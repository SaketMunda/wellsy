import QtQuick

// The results panel (Phase 2). One item per task, newest first: what it is doing,
// the action it is waiting on (Approve / Deny), and its answer with cards, a table,
// candidates and sources. Every value comes from `bridge.hud`, shaped by the runtime
// (engine/voice.py, Link._render). Text that came from the web or from email is shown
// as plain text, never as markup.

Item {
    id: hud
    anchors.fill: parent
    visible: bridge.hudVisible
    opacity: bridge.hudVisible ? 1 : 0
    Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }

    readonly property var items: (bridge.hud && bridge.hud.items) ? bridge.hud.items : []
    readonly property int innerW: panel.width - 44

    Rectangle {
        id: panel
        anchors.fill: parent
        anchors.margins: 20
        radius: 16
        color: Qt.rgba(0.05, 0.07, 0.11, 0.9)
        border.color: Qt.rgba(0.35, 0.55, 0.85, 0.5)
        border.width: 1

        Text {
            id: heading
            x: 22; y: 16
            text: "Wellsy"
            color: "#9fb0cc"; font.pixelSize: 13; font.bold: true; font.letterSpacing: 1.5
        }
        Text {
            anchors.right: parent.right; anchors.rightMargin: 18; y: 12
            text: "×"; color: "#9fb0cc"; font.pixelSize: 20
            MouseArea { anchors.fill: parent; anchors.margins: -8; cursorShape: Qt.PointingHandCursor
                        onClicked: bridge.escape() }
        }

        ListView {
            id: list
            anchors { left: parent.left; right: parent.right; top: heading.bottom; bottom: parent.bottom
                      leftMargin: 22; rightMargin: 22; topMargin: 12; bottomMargin: 18 }
            clip: true
            spacing: 14
            model: hud.items
            delegate: Rectangle {
                id: item
                readonly property var m: modelData
                readonly property bool asking: !!m.approval
                readonly property bool choosing: asking && m.approval.kind === "choose"
                width: hud.innerW
                height: body.implicitHeight + 28
                radius: 12
                color: asking ? Qt.rgba(0.22, 0.16, 0.05, 0.9) : Qt.rgba(1, 1, 1, 0.04)
                border.color: asking ? "#ffcf7a" : Qt.rgba(1, 1, 1, 0.08)
                border.width: asking ? 2 : 1

                Column {
                    id: body
                    x: 14; y: 14
                    width: parent.width - 28
                    spacing: 10

                    // ---- label, status, cancel / dismiss ----
                    Item {
                        width: parent.width; height: 24
                        Text { anchors.verticalCenter: parent.verticalCenter
                               text: item.m.label || ""; color: "#eaf0fb"; font.pixelSize: 16; font.bold: true
                               textFormat: Text.PlainText; elide: Text.ElideRight; width: parent.width - 150 }
                        Row {
                            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                            spacing: 10
                            Text { anchors.verticalCenter: parent.verticalCenter; font.pixelSize: 12
                                   color: item.asking ? "#ffcf7a"
                                        : item.m.status === "done" ? "#8fd6a6"
                                        : item.m.status === "running" ? "#8fbfff" : "#ff9a8a"
                                   text: item.choosing ? "needs your pick" : item.asking ? "needs your yes"
                                       : item.m.status === "running" ? "working…" : (item.m.status || "") }
                            Rectangle {
                                visible: item.m.status === "running"
                                width: 64; height: 24; radius: 6; color: Qt.rgba(1, 1, 1, 0.08)
                                Text { anchors.centerIn: parent; text: "Cancel"; color: "#cdd7ea"; font.pixelSize: 12 }
                                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                            onClicked: bridge.act("cancel", item.m.id) }
                            }
                            Text {
                                visible: item.m.status !== "running"
                                anchors.verticalCenter: parent.verticalCenter
                                text: "×"; color: "#7f8fa8"; font.pixelSize: 16
                                MouseArea { anchors.fill: parent; anchors.margins: -6; cursorShape: Qt.PointingHandCursor
                                            onClicked: bridge.act("dismiss", item.m.id) }
                            }
                        }
                    }

                    // ---- a question: the options, each with where it came from; pick one ----
                    Column {
                        visible: item.choosing
                        width: parent.width
                        spacing: 8
                        Text { text: item.choosing ? item.m.approval.title : ""; color: "#ffe2a8"; width: parent.width
                               font.pixelSize: 15; font.bold: true; wrapMode: Text.Wrap; textFormat: Text.PlainText }
                        Repeater {
                            model: item.choosing ? item.m.approval.options : []
                            Rectangle {
                                width: body.width; height: opt.implicitHeight + 16; radius: 8
                                color: Qt.rgba(1, 0.86, 0.6, 0.08); border.color: Qt.rgba(1, 0.81, 0.48, 0.35)
                                Column {
                                    id: opt
                                    x: 12; y: 8; width: parent.width - 120; spacing: 2
                                    Text { text: (index + 1) + ".  " + modelData.value; color: "#fff4dc"; font.pixelSize: 15
                                           font.bold: true; width: parent.width; elide: Text.ElideRight; textFormat: Text.PlainText }
                                    Text { visible: !!modelData.note; text: modelData.note || ""; color: "#c9b48a"
                                           font.pixelSize: 12; width: parent.width; wrapMode: Text.Wrap; textFormat: Text.PlainText }
                                    Text { visible: !!modelData.source; text: modelData.source || ""; color: "#8fbfff"
                                           font.pixelSize: 11; width: parent.width; elide: Text.ElideMiddle; textFormat: Text.PlainText
                                           MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                                       onClicked: Qt.openUrlExternally(modelData.source) } }
                                }
                                Rectangle {
                                    anchors.right: parent.right; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter
                                    width: 86; height: 34; radius: 8; color: "#2f5f8a"
                                    Text { anchors.centerIn: parent; text: "Pick"; color: "white"; font.bold: true }
                                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                                onClicked: bridge.pick(item.m.approval.id, modelData.value) }
                                }
                            }
                        }
                        Text { color: "#c9b48a"; font.pixelSize: 12; text: "or say which one" }
                    }

                    // ---- the approval: exactly what will happen, then Approve / Deny ----
                    Column {
                        visible: item.asking && !item.choosing
                        width: parent.width
                        spacing: 6
                        Text { text: item.asking ? item.m.approval.title : ""; color: "#ffe2a8"
                               font.pixelSize: 15; font.bold: true; textFormat: Text.PlainText }
                        Repeater {
                            model: item.asking && !item.choosing ? item.m.approval.fields : []
                            Row {
                                spacing: 8
                                Text { width: 110; text: modelData.name; color: "#c9b48a"; font.pixelSize: 13
                                       textFormat: Text.PlainText; horizontalAlignment: Text.AlignRight }
                                Text { width: body.width - 118; text: modelData.value; color: "#fff4dc"
                                       font.pixelSize: 13; wrapMode: Text.Wrap; textFormat: Text.PlainText
                                       maximumLineCount: 8; elide: Text.ElideRight }
                            }
                        }
                        Row {
                            spacing: 12
                            topPadding: 6
                            Rectangle {
                                width: 120; height: 36; radius: 8; color: "#2f7d4f"
                                Text { anchors.centerIn: parent; text: "Approve"; color: "white"; font.bold: true }
                                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                            onClicked: bridge.act("approve", item.m.approval.id) }
                            }
                            Rectangle {
                                width: 120; height: 36; radius: 8; color: "#8a3030"
                                Text { anchors.centerIn: parent; text: "Deny"; color: "white"; font.bold: true }
                                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                            onClicked: bridge.act("deny", item.m.approval.id) }
                            }
                            Text { anchors.verticalCenter: parent.verticalCenter; color: "#c9b48a"; font.pixelSize: 12
                                   text: "or say yes / no · silence is a no" }
                        }
                    }

                    // ---- the answer ----
                    Text { visible: !!item.m.text && !item.asking
                           width: parent.width; wrapMode: Text.Wrap; color: "#eaf0fb"; font.pixelSize: 14
                           textFormat: item.m.status === "done" ? Text.MarkdownText : Text.PlainText
                           text: item.m.text || "" }

                    // candidates to pick from, each with where it came from
                    Repeater {
                        model: item.m.candidates || []
                        Rectangle {
                            width: body.width; height: cand.implicitHeight + 14; radius: 8
                            color: Qt.rgba(0.56, 0.75, 1, 0.08)
                            Column {
                                id: cand
                                x: 10; y: 7; width: parent.width - 20; spacing: 2
                                Text { text: (index + 1) + ".  " + modelData.value; color: "#eaf0fb"; font.pixelSize: 14
                                       font.bold: true; textFormat: Text.PlainText; width: parent.width; elide: Text.ElideRight }
                                Text { visible: !!modelData.note; text: modelData.note || ""; color: "#9fb0cc"
                                       font.pixelSize: 12; textFormat: Text.PlainText; width: parent.width; wrapMode: Text.Wrap }
                                Text { visible: !!modelData.source; text: modelData.source || ""; color: "#8fbfff"
                                       font.pixelSize: 11; textFormat: Text.PlainText; width: parent.width; elide: Text.ElideMiddle
                                       MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                                   onClicked: Qt.openUrlExternally(modelData.source) } }
                            }
                        }
                    }

                    // product / option cards
                    Flow {
                        visible: (item.m.cards || []).length > 0
                        width: parent.width
                        spacing: 10
                        Repeater {
                            model: item.m.cards || []
                            Rectangle {
                                width: 150; height: (modelData.image ? 126 : 6) + 94; radius: 10
                                color: Qt.rgba(1, 1, 1, 0.06)
                                clip: true
                                Image { id: pic; x: 0; y: 0; width: parent.width; height: modelData.image ? 120 : 0
                                        visible: !!modelData.image
                                        fillMode: Image.PreserveAspectCrop; asynchronous: true
                                        source: modelData.image || "" }
                                Column {
                                    x: 8; y: pic.height + 6; width: parent.width - 16; spacing: 3
                                    Text { text: modelData.price || ""; visible: !!modelData.price; color: "#8fd6a6"
                                           font.pixelSize: 14; font.bold: true; textFormat: Text.PlainText }
                                    Text { text: modelData.title; color: "#eaf0fb"; font.pixelSize: 12; width: parent.width
                                           wrapMode: Text.Wrap; maximumLineCount: 2; elide: Text.ElideRight
                                           textFormat: Text.PlainText }
                                    Text { text: modelData.subtitle || ""; color: "#9fb0cc"; font.pixelSize: 11
                                           width: parent.width; elide: Text.ElideRight; textFormat: Text.PlainText }
                                }
                                MouseArea { anchors.fill: parent; enabled: !!modelData.url
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: Qt.openUrlExternally(modelData.url) }
                            }
                        }
                    }

                    // a comparison table
                    Grid {
                        id: grid
                        visible: !!item.m.table
                        readonly property var t: item.m.table || ({ columns: [], rows: [] })
                        readonly property int cols: Math.max(1, t.columns.length)
                        columns: cols
                        columnSpacing: 1; rowSpacing: 1
                        Repeater {
                            model: grid.t.columns
                            Rectangle { width: (body.width - grid.cols) / grid.cols; height: hc.implicitHeight + 10
                                        color: Qt.rgba(0.56, 0.75, 1, 0.14)
                                Text { id: hc; x: 6; y: 5; width: parent.width - 12; text: modelData; color: "#eaf0fb"
                                       font.pixelSize: 12; font.bold: true; wrapMode: Text.Wrap; textFormat: Text.PlainText } }
                        }
                        Repeater {
                            model: [].concat.apply([], grid.t.rows.map(function (r) {
                                var row = r.slice(0, grid.cols); while (row.length < grid.cols) row.push(""); return row }))
                            Rectangle { width: (body.width - grid.cols) / grid.cols; height: cc.implicitHeight + 10
                                        color: Qt.rgba(1, 1, 1, 0.04)
                                Text { id: cc; x: 6; y: 5; width: parent.width - 12; text: String(modelData); color: "#cdd7ea"
                                       font.pixelSize: 12; wrapMode: Text.Wrap; textFormat: Text.PlainText } }
                        }
                    }

                    // what was approved or blocked, in this task
                    Repeater {
                        model: item.m.actions || []
                        Text { text: "• " + modelData; font.pixelSize: 12; textFormat: Text.PlainText
                               color: modelData.indexOf("approved") >= 0 ? "#8fd6a6" : "#ff9a8a" }
                    }

                    // sources
                    Repeater {
                        model: item.m.sources || []
                        Text { width: body.width; color: "#8fbfff"; font.pixelSize: 12; elide: Text.ElideRight
                               textFormat: Text.PlainText
                               text: (index + 1) + ". " + (modelData.title || modelData.url)
                               MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                           onClicked: Qt.openUrlExternally(modelData.url) } }
                    }

                    Text { visible: !!item.m.meta; text: item.m.meta || ""; color: "#7f8fa8"; font.pixelSize: 11 }
                }
            }
        }
    }

    // Esc hides the panel; tasks keep running and it comes back on the next change.
    Keys.onEscapePressed: bridge.escape()
    focus: bridge.hudVisible
}
