import type { Lead, Vertical } from "./types";
const names = ["Martín Demo","Laura Ejemplo","Nicolás Prueba","Sofía Ficticia","Tomás Muestra","Valentina Demo","Agustín Ejemplo","Camila Prueba","Bruno Ficticio","Julieta Muestra","Mateo Demo","Emilia Ejemplo"];
const provinces = ["Santa Fe","Córdoba","Buenos Aires","Entre Ríos","Mendoza","La Pampa"];
const statuses = ["Nuevo","Contactado","Calificado","Propuesta","Ganado","Perdido"] as const;
const priorities = ["Alta","Media","Baja"] as const;
const brands = ["Case IH","New Holland","Case IH","New Holland"];
const machines = ["Cosechadora","Tractor","Sembradora","Pulverizadora"];
const now = Date.now();
function common(index:number, vertical:Vertical): Lead {
  const phone = `+54 9 342 555 ${String(1100 + index).padStart(4,"0")}`;
  return { id:`demo_${vertical}_${index+1}`, vertical, name:names[index], persona:names[index], province:provinces[index%provinces.length], provincia:provinces[index%provinces.length], phone, telefono:phone, channel:index===8?"messenger":"whatsapp", assigned_to:index%3?"Sin asignar":"Equipo comercial", status:statuses[index%6], _status:statuses[index%6], priority:priorities[index%3], _priority:priorities[index%3], created_at:new Date(now-(index+1)*3600000).toISOString(), fecha_iso:new Date(now-(index+1)*3600000).toISOString(), score:90-index*4, source:"demo", source_label:index===8?"Messenger":"WhatsApp", whatsapp_confirmed:index!==8, _isDemo:true };
}
export const DEMO_FOTOMULTAS: Lead[] = names.map((_,i)=>({ ...common(i,"fotomultas"), snippet:["Transferencia detenida por una infracción pendiente.","Consulta por fotomulta de velocidad en ruta.","Necesita presentar un descargo antes del vencimiento."][i%3], vertical_data:{ plate:`DE${String(100+i).padStart(3,"0")}MO`, municipality:["Santa Fe","Rosario","Córdoba"][i%3], violation_type:["Exceso de velocidad","Semáforo en rojo","Estacionamiento"][i%3], estimated_amount:120000+i*7500, due_date:"2026-08-10" } }));
export const DEMO_REPUESTOS: Lead[] = names.map((_,i)=>({ ...common(i,"repuestos_agricolas"), snippet:["Busca disponibilidad inmediata para la próxima campaña.","Solicita cotización y plazo de entrega del repuesto.","Necesita reemplazo urgente para volver a trabajar."][i%3], vertical_data:{ brand:brands[i%4], machine_type:machines[i%4], model:["Axial-Flow 7130","T7.245","Precision 500","Patriot 350"][i%4], part_number:`FX-${87312000+i*17}`, quantity:i%3+1, urgency:priorities[i%3].toLowerCase() } }));
export const DEMO_LEADS=[...DEMO_FOTOMULTAS,...DEMO_REPUESTOS];
export const demoByVertical=(vertical:Vertical)=>vertical==="fotomultas"?DEMO_FOTOMULTAS:DEMO_REPUESTOS;
