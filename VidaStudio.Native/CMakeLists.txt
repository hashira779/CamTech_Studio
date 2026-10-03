cmake_minimum_required(VERSION 3.15)
project(VidaStudioNative VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Configure as a DLL
add_library(VidaStudioNative SHARED
    dllmain.cpp
    FFT.h
    FFT.cpp
    SpectrumSmoother.h
    SpectrumSmoother.cpp
    D3D11Renderer.h
    D3D11Renderer.cpp
)

# Compile HLSL Shader
set(SHADER_FILE "${CMAKE_CURRENT_SOURCE_DIR}/SpectrumShader.hlsl")
set(SHADER_OBJ "${CMAKE_CURRENT_BINARY_DIR}/SpectrumShader.cso")

add_custom_command(
    TARGET VidaStudioNative PRE_BUILD
    COMMAND fxc.exe /T vs_5_0 /E VSMain /Fo "${CMAKE_CURRENT_BINARY_DIR}/VSMain.cso" "${SHADER_FILE}"
    COMMAND fxc.exe /T ps_5_0 /E PSMain /Fo "${CMAKE_CURRENT_BINARY_DIR}/PSMain.cso" "${SHADER_FILE}"
    COMMENT "Compiling HLSL Shaders..."
)

# Link against D3D11 and DXGI
target_link_libraries(VidaStudioNative PRIVATE d3d11 dxgi d3dcompiler)

# Define export macros if needed, though we use __declspec(dllexport) explicitly.
target_compile_definitions(VidaStudioNative PRIVATE "VIDASTUDIONATIVE_EXPORTS")
