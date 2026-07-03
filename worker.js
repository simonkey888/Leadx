export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    
    // Si es la raíz, servir index.html
    if (url.pathname === '/' || url.pathname === '/index.html') {
      return env.ASSETS.fetch(new Request('https://example.com/index.html'));
    }
    
    // Para todo lo demás, intentar servir desde assets
    return env.ASSETS.fetch(request);
  }
};
