import QtQuick

// The Presence orb. Borderless / translucent / click-through window flags are
// set on the QQuickView in backend.py; this item is only the visual.
//
// Every animated quantity here is bound to `bridge`, the QObject the backend
// updates from measured SignalBus state. `bridge.reactiveAmplitude` is the only
// thing that scales the pulse. There is no NumberAnimation on it, no Timer
// feeding it — grep this file.

Item {
    id: root
    width: 160; height: 160

    // per-state palette + glow. Chosen from bridge.state (a string), not animated.
    readonly property var palette: ({
        "asleep":            { c: Qt.rgba(0.30,0.34,0.42,1), g: 0.02 },
        "idle":              { c: Qt.rgba(0.45,0.62,0.85,1), g: 0.10 },
        "listening":         { c: Qt.rgba(0.30,0.78,1.00,1), g: 0.35 },
        "thinking":          { c: Qt.rgba(0.62,0.55,0.95,1), g: 0.25 },
        "acting":            { c: Qt.rgba(0.40,0.85,0.60,1), g: 0.30 },
        "awaiting_approval": { c: Qt.rgba(1.00,0.75,0.20,1), g: 0.55 },
        "refusing":          { c: Qt.rgba(1.00,0.32,0.32,1), g: 0.50 },
        "speaking":          { c: Qt.rgba(0.55,0.80,1.00,1), g: 0.40 }
    })
    readonly property var pal: palette[bridge.state] || palette["idle"]

    // Colour eases between states (a palette cross-fade is not a lie about
    // system state — the state itself switches instantly). Amplitude does NOT
    // ease; it is the measurement.
    Behavior on effectColor { ColorAnimation { duration: 220 } }
    property color effectColor: pal.c
    property real effectGlow: pal.g
    Behavior on effectGlow { NumberAnimation { duration: 220 } }

    ShaderEffect {
        id: fx
        anchors.fill: parent
        blending: true

        property real uTime: 0.0
        property real uAmplitude: bridge.reactiveAmplitude   // MEASURED, direct bind
        property real uGlow: root.effectGlow
        property color uColor: root.effectColor

        fragmentShader: "shaders/orb.frag.qsb"

        // uTime advances only while the window is exposed AND either the orb is
        // reactive or awake-idle; asleep throttles hard (perf budget < 1%).
        FrameAnimation {
            running: Qt.application.active || bridge.state !== "asleep"
            onTriggered: fx.uTime += (bridge.state === "asleep" ? 0.05 : frameTime)
        }
    }

    // explicit grab affordance — the ONLY non-click-through region. Drag moves
    // the window; position is persisted by the backend on release.
    Rectangle {
        id: grip
        width: 26; height: 26; radius: 13
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        color: Qt.rgba(1,1,1, dragArea.containsMouse ? 0.22 : 0.0)
        Behavior on color { ColorAnimation { duration: 150 } }
        MouseArea {
            id: dragArea
            anchors.fill: parent
            hoverEnabled: true
            property point press
            onPressed: (m) => press = Qt.point(m.x, m.y)
            onPositionChanged: (m) => bridge.dragBy(m.x - press.x, m.y - press.y)
            onReleased: bridge.persistPosition()
        }
    }

    // a11y / debug: the reason string, shown only when HUD asks for it
    property alias becauseText: because.text
    Text {
        id: because
        visible: bridge.showBecause
        anchors { top: parent.bottom; horizontalCenter: parent.horizontalCenter }
        color: "#cfd6e4"; font.pixelSize: 10
        text: bridge.because
    }
}
