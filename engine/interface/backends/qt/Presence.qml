import QtQuick
import Wellsy.Orb

// The Presence orb — Wellsy.Orb.PointCloud: a ~5.5k-point sphere that unravels
// into swirling cyan→violet→magenta ribbons and re-winds. Modelled on the
// reference clip; drawn on the Qt scene graph, in-process (teardown D54).
//
// Honesty (INVARIANTS #6 → pixels): `cloud.amplitude` is bound straight to
// bridge.reactiveAmplitude — the ONLY reactive input, 0 unless a live VAD / PCM
// frame exists. `cloud.tick(frameTime)` advances the swirl clock (the one
// motion allowed on a timer — "the runtime is up"). `cloud.state` picks a
// per-state identity, eased inside the item. Grep: nothing here feeds amplitude.

Item {
    id: root
    width: 170; height: 200

    readonly property string orbState: bridge ? bridge.state : "asleep"

    PointCloud {
        id: cloud
        width: 170; height: 170
        anchors.top: parent.top
        anchors.horizontalCenter: parent.horizontalCenter
        state: root.orbState
        amplitude: bridge ? bridge.reactiveAmplitude : 0.0   // MEASURED, direct bind
        opacity: 1.0
        renderTarget: PointCloud.FramebufferObject
    }

    // Adaptive repaint: ~60 fps when the orb is doing something, ~6 fps when
    // asleep — the perf budget requires it to throttle at rest (< 1% asleep).
    Timer {
        id: pump
        property double last: 0
        running: true
        repeat: true
        // asleep barely moves; idle drifts gently at ~15 fps; anything the user
        // is actually interacting with gets the full ~60 fps.
        interval: root.orbState === "asleep" ? 220
                : (root.orbState === "idle" ? 90 : 16)
        onTriggered: {
            var now = Date.now() / 1000.0
            var dt = last > 0 ? Math.min(0.25, now - last) : interval / 1000.0
            last = now
            cloud.tick(dt)
        }
    }

    // explicit grab affordance — the only non-click-through region
    Rectangle {
        id: grip
        width: 26; height: 26; radius: 13
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        color: Qt.rgba(1, 1, 1, dragArea.containsMouse ? 0.22 : 0.0)
        Behavior on color { ColorAnimation { duration: 150 } }
        MouseArea {
            id: dragArea
            anchors.fill: parent
            hoverEnabled: true
            property point press
            onPressed: (m) => press = Qt.point(m.x, m.y)
            onPositionChanged: (m) => { if (bridge) bridge.dragBy(m.x - press.x, m.y - press.y) }
            onReleased: { if (bridge) bridge.persistPosition() }
        }
    }

    Text {
        visible: bridge ? bridge.showBecause : false
        anchors { top: cloud.bottom; horizontalCenter: parent.horizontalCenter }
        color: "#cfd6e4"; font.pixelSize: 10
        text: bridge ? bridge.because : ""
    }
}
