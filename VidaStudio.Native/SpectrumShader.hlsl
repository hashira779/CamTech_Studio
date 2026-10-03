// Vertex Shader Input
struct VS_INPUT {
    // Vertex buffer (per-vertex)
    float2 Pos : POSITION;
    
    // Instance buffer (per-instance)
    float4 Color : INSTANCE_COLOR;
    float2 InstPos : INSTANCE_POS;
    float2 InstSize : INSTANCE_SIZE;
};

// Pixel Shader Input / Vertex Shader Output
struct PS_INPUT {
    float4 Pos : SV_POSITION;
    float4 Color : COLOR;
    float2 UV : TEXCOORD0;
};

PS_INPUT VSMain(VS_INPUT input) {
    PS_INPUT output;
    
    // Scale and translate the quad based on instance data
    float2 scaledPos = input.Pos * input.InstSize;
    float2 finalPos = scaledPos + input.InstPos;
    
    output.Pos = float4(finalPos, 0.0f, 1.0f);
    output.Color = input.Color;
    output.UV = input.Pos; // 0 to 1 over the quad
    
    return output;
}

float4 PSMain(PS_INPUT input) : SV_TARGET {
    // Create a smooth gradient from bottom to top
    float gradient = 1.0f - input.UV.y; 
    
    // Smooth anti-aliased edge (rounded caps effect can be added here)
    float edgeX = 1.0f - abs(input.UV.x - 0.5f) * 2.0f;
    float alpha = smoothstep(0.0f, 0.1f, edgeX);
    
    // Bloom/glow multiplier
    float glow = 1.5f; 
    
    float4 finalColor = input.Color * gradient * glow;
    finalColor.a = alpha;
    
    return finalColor;
}
