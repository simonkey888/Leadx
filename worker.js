/**
 * Radar Leads PRO — Cloudflare Worker
 *
 * Sirve archivos estáticos desde ./public/
 * JSONs van con Cache-Control: no-store para que el dashboard siempre
 * vea datos frescos sin pelearte con caché del browser.
 */
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

    // --- JSON endpoints: Cache-Control: no-store ---
    // CRÍTICO: sin esto el browser cachea el JSON y el dashboard
    // parece que no actualiza aunque el pipeline corra.
    if (path.endsWith('.json')) {
      const response = await env.ASSETS.fetch(request);
      const newResponse = new Response(response.body, response);
      newResponse.headers.set('Cache-Control', 'no-store, no-cache, must-revalidate');
      newResponse.headers.set('Pragma', 'no-cache');
      newResponse.headers.set('Expires', '0');
      newResponse.headers.set('Content-Type', 'application/json; charset=utf-8');
      return newResponse;
    }

    // --- HTML: cache moderado (5 min) ---
    if (path === '/' || path === '/index.html' || path.endsWith('.html')) {
      const response = await env.ASSETS.fetch(
        new Request(path === '/' ? 'https://example.com/index.html' : request.url)
      );
      const newResponse = new Response(response.body, response);
      newResponse.headers.set('Cache-Control', 'public, max-age=300');
      return newResponse;
    }

    // --- Todo lo demás: servir directo ---
    return env.ASSETS.fetch(request);
  }
};
