#pragma once
#include <d3d11_1.h>
#include <DirectXMath.h>
#include <vector>
#include <wrl/client.h>
#include <windows.ui.xaml.media.dxinterop.h>

struct InstanceData {
    DirectX::XMFLOAT4 Color;
    DirectX::XMFLOAT2 Position;
    DirectX::XMFLOAT2 Size;
};

class D3D11Renderer
{
public:
    D3D11Renderer();
    ~D3D11Renderer();

    bool Initialize(ISwapChainPanelNative* panel, int width, int height);
    void Resize(int width, int height);
    void Render(const std::vector<float>& bands);

private:
    bool CreateDeviceResources();
    bool CreateSizeDependentResources();
    bool CreateShaders();
    bool CreateBuffers();

    int m_width;
    int m_height;

    Microsoft::WRL::ComPtr<ID3D11Device1> m_d3dDevice;
    Microsoft::WRL::ComPtr<ID3D11DeviceContext1> m_d3dContext;
    Microsoft::WRL::ComPtr<IDXGISwapChain1> m_swapChain;
    Microsoft::WRL::ComPtr<ID3D11RenderTargetView> m_renderTargetView;
    Microsoft::WRL::ComPtr<ISwapChainPanelNative> m_panel;

    Microsoft::WRL::ComPtr<ID3D11VertexShader> m_vertexShader;
    Microsoft::WRL::ComPtr<ID3D11PixelShader> m_pixelShader;
    Microsoft::WRL::ComPtr<ID3D11InputLayout> m_inputLayout;

    Microsoft::WRL::ComPtr<ID3D11Buffer> m_vertexBuffer; // Base quad
    Microsoft::WRL::ComPtr<ID3D11Buffer> m_instanceBuffer; // Bar instances

    int m_maxBands;
};
