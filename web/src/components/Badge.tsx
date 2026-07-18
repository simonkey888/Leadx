import type {Lead} from "../types";
export function Badge({lead}:{lead:Lead}){const status=lead._status||lead.status||"Nuevo";const priority=lead._priority||lead.priority||"Media";return <span className={`badge badge--${String(status).toLowerCase().replace(" ","-")}`}>{status} · {priority}</span>}
