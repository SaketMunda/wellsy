import QtQuick

// HUD mode — panels that unfold *from* the orb. Cinematic (depth, glow,
// translucency, the scale/opacity unfold) but every value is real: it is
// whatever `bridge.hud` (a plain JS object shaped by the runtime) contains.
// No decorative telemetry, no fake scrolling numbers.

Item {
    id: hud
    anchors.fill: parent
    visible: bridge.hudVisible
    opacity: bridge.hudVisible ? 1 : 0
    Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }

    readonly property var model: bridge.hud

    Rectangle {
        id: panel
        anchors.centerIn: parent
        width: Math.min(parent.width - 80, 720)
        height: Math.min(parent.height - 80, 520)
        radius: 16
        color: Qt.rgba(0.05, 0.07, 0.11, 0.86)
        border.color: Qt.rgba(0.35, 0.55, 0.85, 0.5)
        border.width: 1

        transform: Scale {
            origin.x: panel.width / 2; origin.y: panel.height / 2
            xScale: bridge.hudVisible ? 1 : 0.6
            yScale: bridge.hudVisible ? 1 : 0.6
            Behavior on xScale { NumberAnimation { duration: 200; easing.type: Easing.OutBack } }
            Behavior on yScale { NumberAnimation { duration: 200; easing.type: Easing.OutBack } }
        }

        Column {
            anchors.fill: parent
            anchors.margins: 22
            spacing: 14

            Text {
                text: hud.model && hud.model.kind === "approval"
                      ? "Approve this action?"
                      : (hud.model ? hud.model.title || "" : "")
                color: "#eaf0fb"; font.pixelSize: 20; font.bold: true
            }

            // ---- approval prompt: the most important screen in the product ----
            Loader {
                active: hud.model && hud.model.kind === "approval"
                width: parent.width
                sourceComponent: Column {
                    spacing: 8
                    Text { color: "#cdd7ea"; font.pixelSize: 14
                           text: "tool:  " + (hud.model.tool || "") }
                    Text { color: "#cdd7ea"; font.pixelSize: 13
                           text: "args:  " + JSON.stringify(hud.model.args || {}) }
                    Text { color: "#ffcf7a"; font.pixelSize: 13
                           text: "risk:  " + hud.model.risk
                                 + "   reversible: " + (hud.model.reversible ? "yes" : "no") }
                    Text { color: "#9fb0cc"; font.pixelSize: 12; wrapMode: Text.Wrap
                           width: panel.width - 44
                           text: hud.model.reason || "" }
                    Row {
                        spacing: 12
                        Rectangle {
                            width: 120; height: 38; radius: 8; color: "#2f7d4f"
                            Text { anchors.centerIn: parent; text: "Approve"; color: "white" }
                            MouseArea { anchors.fill: parent; onClicked: bridge.answerApproval(true) }
                        }
                        Rectangle {
                            width: 120; height: 38; radius: 8; color: "#8a3030"
                            Text { anchors.centerIn: parent; text: "Deny"; color: "white" }
                            MouseArea { anchors.fill: parent; onClicked: bridge.answerApproval(false) }
                        }
                    }
                }
            }

            // ---- plan, with each step's real policy decision beside it ----
            Loader {
                active: hud.model && hud.model.kind === "plan"
                width: parent.width
                sourceComponent: ListView {
                    width: panel.width - 44
                    height: panel.height - 120
                    clip: true
                    model: hud.model.steps || []
                    delegate: Row {
                        spacing: 10
                        Text { color: "#eaf0fb"; font.pixelSize: 13
                               text: (index + 1) + ". " + (modelData.tool || "") }
                        Text { font.pixelSize: 12
                               color: modelData.decision === "deny" ? "#ff7a7a"
                                    : modelData.decision === "confirm" ? "#ffcf7a" : "#8fd6a6"
                               text: "[" + (modelData.decision || "allow") + "]" }
                    }
                }
            }

            // ---- read-back verification (INVARIANTS #15) ----
            Loader {
                active: hud.model && hud.model.kind === "verify"
                width: parent.width
                sourceComponent: Column {
                    spacing: 6
                    Text { color: "#cdd7ea"; font.pixelSize: 13
                           text: "claimed:  " + (hud.model.claimed || "") }
                    Text { font.pixelSize: 13
                           color: hud.model.verified ? "#8fd6a6" : "#ff7a7a"
                           text: (hud.model.verified ? "confirmed by " : "NOT confirmed — ")
                                 + (hud.model.method || "") }
                }
            }
        }
    }

    // Esc closes the HUD and routes to the deterministic stop path in backend.
    Keys.onEscapePressed: bridge.escape()
    focus: bridge.hudVisible
}
