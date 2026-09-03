#version 440
// WELLSY Presence orb — Qt 6 RHI fragment shader (Vulkan-flavoured GLSL).
// Compiled to orb.frag.qsb by build_shaders.py (SPIR-V + MSL/HLSL/GLSL).
//
// HONESTY BOUNDARY (INVARIANTS #6 -> pixels):
//   uAmplitude  — the pulse. Traces to derive_state().reactive_amplitude, i.e.
//                 a live VAD or output-PCM RMS. 0.0 => the surface does not
//                 pulse. There is no other input that scales the displacement.
//   uTime       — drives ONLY the fixed-magnitude domain warp (the "breathing"
//                 that says the pipeline is up). It never touches uAmplitude and
//                 its contribution to the radius is clamped to BREATH_MAX.
//   uColor/uGlow — per-state palette, set from the state name, not animated.

layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;

layout(std140, binding = 0) uniform buf {
    mat4  qt_Matrix;
    float qt_Opacity;
    float uTime;        // seconds, monotonic
    float uAmplitude;   // 0..1, MEASURED
    float uGlow;        // 0..1, per-state
    vec4  uColor;       // per-state rgb
};

const float BREATH_MAX = 0.015;   // max radius contribution from uTime, ever

// cheap 2D value-noise fbm
float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p){
    vec2 i = floor(p), f = fract(p);
    vec2 u = f*f*(3.0-2.0*f);
    return mix(mix(hash(i+vec2(0,0)), hash(i+vec2(1,0)), u.x),
               mix(hash(i+vec2(0,1)), hash(i+vec2(1,1)), u.x), u.y);
}
float fbm(vec2 p){
    float v = 0.0, a = 0.5;
    for (int k = 0; k < 4; ++k){ v += a*noise(p); p *= 2.0; a *= 0.5; }
    return v;
}

void main(){
    vec2 uv = qt_TexCoord0 * 2.0 - 1.0;      // -1..1
    float r = length(uv);
    float ang = atan(uv.y, uv.x);

    // breathing: fixed tiny in/out, purely time-based, hard-capped.
    float breath = BREATH_MAX * sin(uTime * 1.3);

    // reactive displacement: ONLY uAmplitude scales this term.
    float wob = fbm(vec2(cos(ang), sin(ang)) * 3.0 + uTime * 0.25);
    float disp = uAmplitude * 0.16 * (wob - 0.5);

    float edge = 0.72 + breath + disp;
    float body = smoothstep(edge, edge - 0.16, r);          // filled disc
    float rim  = smoothstep(edge - 0.03, edge, r) * smoothstep(edge + 0.10, edge, r);
    float fres = pow(1.0 - clamp(1.0 - r / edge, 0.0, 1.0), 3.0); // Fresnel-ish

    vec3 col = uColor.rgb * (0.35 + 0.65 * body);
    col += uColor.rgb * rim * (1.2 + 2.0 * uGlow);
    col += uColor.rgb * fres * 0.5;

    float alpha = clamp(body + rim * (0.6 + uGlow), 0.0, 1.0) * qt_Opacity;
    fragColor = vec4(col * alpha, alpha);   // premultiplied
}
