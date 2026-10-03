#include "D3D11Renderer.h"
#include <d3dcompiler.h>
#include <iostream>

#pragma comment(lib, "d3d11.lib")
#pragma comment(lib, "dxgi.lib")
#pragma comment(lib, "d3dcompiler.lib")

using namespace Microsoft::WRL;
using namespace DirectX;

struct Vertex {
    XMFLOAT2 Pos;
};

D3D11Renderer::D3D11Renderer() : m_width(1920), m_height(1080), m_maxBands(256) {}
D3D11Renderer::~D3D11Renderer() {}

bool D3D11Renderer::Initialize(ISwapChainPanelNative* panel, int width, int height)
{
    m_panel = panel;
    m_width = width;
    m_height = height;

    if (!CreateDeviceResources()) return false;
    if (!CreateSizeDependentResources()) return false;
    if (!CreateBuffers()) return false;
    // We assume CreateShaders() will be called externally or here if HLSL is compiled at runtime.
    
    return true;
}

bool D3D11Renderer::CreateDeviceResources()
{
    UINT creationFlags = D3D11_CREATE_DEVICE_BGRA_SUPPORT;
#if defined(_DEBUG)
    creationFlags |= D3D11_CREATE_DEVICE_DEBUG;
#endif

    D3D_FEATURE_LEVEL featureLevels[] = {
        D3D_FEATURE_LEVEL_11_1,
        D3D_FEATURE_LEVEL_11_0,
        D3D_FEATURE_LEVEL_10_1,
        D3D_FEATURE_LEVEL_10_0,
    };

    ComPtr<ID3D11Device> device;
    ComPtr<ID3D11DeviceContext> context;

    HRESULT hr = D3D11CreateDevice(
        nullptr, D3D_DRIVER_TYPE_HARDWARE, nullptr, creationFlags,
        featureLevels, ARRAYSIZE(featureLevels), D3D11_SDK_VERSION,
        &device, nullptr, &context);

    if (FAILED(hr)) return false;

    device.As(&m_d3dDevice);
    context.As(&m_d3dContext);

    return true;
}

bool D3D11Renderer::CreateSizeDependentResources()
{
    if (m_swapChain != nullptr)
    {
        m_renderTargetView.Reset();
        m_swapChain->ResizeBuffers(2, m_width, m_height, DXGI_FORMAT_B8G8R8A8_UNORM, 0);
    }
    else
    {
        DXGI_SWAP_CHAIN_DESC1 swapChainDesc = {0};
        swapChainDesc.Width = m_width;
        swapChainDesc.Height = m_height;
        swapChainDesc.Format = DXGI_FORMAT_B8G8R8A8_UNORM;
        swapChainDesc.Stereo = false;
        swapChainDesc.SampleDesc.Count = 1;
        swapChainDesc.SampleDesc.Quality = 0;
        swapChainDesc.BufferUsage = DXGI_USAGE_RENDER_TARGET_OUTPUT;
        swapChainDesc.BufferCount = 2;
        swapChainDesc.SwapEffect = DXGI_SWAP_EFFECT_FLIP_SEQUENTIAL;
        swapChainDesc.Flags = 0;
        swapChainDesc.AlphaMode = DXGI_ALPHA_MODE_PREMULTIPLIED;

        ComPtr<IDXGIDevice3> dxgiDevice;
        m_d3dDevice.As(&dxgiDevice);

        ComPtr<IDXGIAdapter> dxgiAdapter;
        dxgiDevice->GetAdapter(&dxgiAdapter);

        ComPtr<IDXGIFactory3> dxgiFactory;
        dxgiAdapter->GetParent(IID_PPV_ARGS(&dxgiFactory));

        HRESULT hr = dxgiFactory->CreateSwapChainForComposition(
            m_d3dDevice.Get(), &swapChainDesc, nullptr, &m_swapChain);

        if (FAILED(hr)) return false;

        if (m_panel)
        {
            m_panel->SetSwapChain(m_swapChain.Get());
        }
    }

    ComPtr<ID3D11Texture2D> backBuffer;
    m_swapChain->GetBuffer(0, IID_PPV_ARGS(&backBuffer));
    m_d3dDevice->CreateRenderTargetView(backBuffer.Get(), nullptr, &m_renderTargetView);

    D3D11_VIEWPORT viewport = { 0.0f, 0.0f, (float)m_width, (float)m_height, 0.0f, 1.0f };
    m_d3dContext->RSSetViewports(1, &viewport);

    return true;
}

void D3D11Renderer::Resize(int width, int height)
{
    m_width = width;
    m_height = height;
    CreateSizeDependentResources();
}

bool D3D11Renderer::CreateBuffers()
{
    // A simple quad from (0,0) to (1,1). Instance size & pos will transform it.
    Vertex vertices[] = {
        { XMFLOAT2(0.0f, 0.0f) },
        { XMFLOAT2(1.0f, 0.0f) },
        { XMFLOAT2(0.0f, 1.0f) },
        { XMFLOAT2(1.0f, 1.0f) },
    };

    D3D11_BUFFER_DESC bd = {};
    bd.Usage = D3D11_USAGE_DEFAULT;
    bd.ByteWidth = sizeof(vertices);
    bd.BindFlags = D3D11_BIND_VERTEX_BUFFER;

    D3D11_SUBRESOURCE_DATA initData = {};
    initData.pSysMem = vertices;

    if (FAILED(m_d3dDevice->CreateBuffer(&bd, &initData, &m_vertexBuffer))) return false;

    // Instance Buffer for up to 256 bands (dynamic)
    D3D11_BUFFER_DESC ibd = {};
    ibd.Usage = D3D11_USAGE_DYNAMIC;
    ibd.ByteWidth = sizeof(InstanceData) * m_maxBands;
    ibd.BindFlags = D3D11_BIND_VERTEX_BUFFER;
    ibd.CPUAccessFlags = D3D11_CPU_ACCESS_WRITE;

    if (FAILED(m_d3dDevice->CreateBuffer(&ibd, nullptr, &m_instanceBuffer))) return false;

    return true;
}

void D3D11Renderer::Render(const std::vector<float>& bands)
{
    if (!m_d3dContext || !m_renderTargetView) return;

    // Clear background
    const float clearColor[] = { 0.05f, 0.05f, 0.08f, 1.0f };
    m_d3dContext->ClearRenderTargetView(m_renderTargetView.Get(), clearColor);

    // Update instance buffer
    D3D11_MAPPED_SUBRESOURCE mappedResource;
    m_d3dContext->Map(m_instanceBuffer.Get(), 0, D3D11_MAP_WRITE_DISCARD, 0, &mappedResource);
    InstanceData* data = (InstanceData*)mappedResource.pData;

    int numBands = (int)bands.size();
    float totalWidth = 2.0f; // Screen goes from -1 to 1 in clip space
    float spacing = 0.01f;
    float barW = (totalWidth - (spacing * (numBands + 1))) / numBands;

    for (int i = 0; i < numBands; ++i)
    {
        float val = bands[i];
        data[i].Size = XMFLOAT2(barW, val * 1.5f); // Scale height
        data[i].Position = XMFLOAT2(-1.0f + spacing + (i * (barW + spacing)), -1.0f);
        
        // Dynamic coloring (blue to pink based on height)
        data[i].Color = XMFLOAT4(val, 0.3f, 1.0f - val, 1.0f);
    }

    m_d3dContext->Unmap(m_instanceBuffer.Get(), 0);

    // Bind and draw
    m_d3dContext->OMSetRenderTargets(1, m_renderTargetView.GetAddressOf(), nullptr);

    UINT strides[2] = { sizeof(Vertex), sizeof(InstanceData) };
    UINT offsets[2] = { 0, 0 };
    ID3D11Buffer* buffers[2] = { m_vertexBuffer.Get(), m_instanceBuffer.Get() };

    m_d3dContext->IASetVertexBuffers(0, 2, buffers, strides, offsets);
    m_d3dContext->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLESTRIP);

    if (m_vertexShader && m_pixelShader)
    {
        m_d3dContext->VSSetShader(m_vertexShader.Get(), nullptr, 0);
        m_d3dContext->PSSetShader(m_pixelShader.Get(), nullptr, 0);
        m_d3dContext->IASetInputLayout(m_inputLayout.Get());
        
        m_d3dContext->DrawInstanced(4, numBands, 0, 0);
    }

    m_swapChain->Present(1, 0); // Sync to 60fps VSync
}
