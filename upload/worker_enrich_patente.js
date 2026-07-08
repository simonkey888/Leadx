// ═══════════════════════════════════════════════════════════════════════════════
// LEADX WORKER.JS - Endpoint /api/enrich-patente
// Recibe enriquecimiento de patentes desde GH Actions y actualiza KV
// ═══════════════════════════════════════════════════════════════════════════════

// Agregar este case al router principal del Worker:

async function handleEnrichPatente(request, env) {
  // Verificar secret
  const secret = request.headers.get('X-Ingest-Secret');
  if (secret !== env.INGEST_SECRET) {
    return new Response(JSON.stringify({ error: 'Unauthorized' }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' }
    });
  }

  const payload = await request.json();

  // Validar payload
  if (!payload.lead_id || !payload.patentes) {
    return new Response(JSON.stringify({ error: 'Invalid payload' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' }
    });
  }

  const leadId = payload.lead_id;

  // Recuperar lead actual desde KV
  const leadKey = `lead:${leadId}`;
  const existingData = await env.LEADX_KV.get(leadKey, { type: 'json' });

  if (!existingData) {
    return new Response(JSON.stringify({ error: 'Lead not found' }), {
      status: 404,
      headers: { 'Content-Type': 'application/json' }
    });
  }

  // Merge de datos: deep merge por ID
  const enrichedLead = {
    ...existingData,
    patentes: payload.patentes,
    score_boost: payload.score_boost || 0,
    dnrpa_links: payload.dnrpa_links || [],
    enrichment_timestamp: payload.timestamp,
    enrichment_type: 'patente_extraction',

    // Actualizar score total
    score: Math.min(100, (existingData.score || 0) + (payload.score_boost || 0)),

    // Agregar a score_explain
    score_explain: [
      ...(existingData.score_explain || []),
      `Patente extraída: ${payload.patentes.map(p => p.patente).join(', ')} (+${payload.score_boost || 0})`
    ],

    // Actualizar contacto sugerido si no hay teléfono
    contacto_sugerido: existingData.phone 
      ? 'whatsapp' 
      : existingData.fb_contact_id 
        ? 'messenger' 
        : payload.dnrpa_links?.length > 0 
          ? 'dnrpa_manual' 
          : 'sin_contacto'
  };

  // Guardar en KV
  await env.LEADX_KV.put(leadKey, JSON.stringify(enrichedLead));

  // Actualizar índice de patentes para búsqueda rápida
  for (const patente of payload.patentes) {
    const patenteKey = `patente:${patente.patente.replace(/\s/g, '')}`;
    const patenteIndex = await env.LEADX_KV.get(patenteKey, { type: 'json' }) || { leads: [] };

    if (!patenteIndex.leads.includes(leadId)) {
      patenteIndex.leads.push(leadId);
      await env.LEADX_KV.put(patenteKey, JSON.stringify(patenteIndex));
    }
  }

  return new Response(JSON.stringify({
    success: true,
    lead_id: leadId,
    patentes_enriched: payload.patentes.length,
    new_score: enrichedLead.score
  }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' }
  });
}

// Agregar al router principal:
// case '/api/enrich-patente': return handleEnrichPatente(request, env);
