# LeadX — política de sesión autenticada

## Configuración vigente en este release

La sesión protegida por contraseña usa dos límites independientes:

- inactividad máxima: **60 minutos**;
- duración absoluta desde el login: **12 horas**.

Constantes canónicas:

```text
SESSION_IDLE_MS=60 * 60 * 1000
SESSION_ABSOLUTE_MS=12 * 60 * 60 * 1000
SESSION_RENEW_MIN_MS=60 * 1000
```

## Comportamiento

1. El login correcto emite una cookie de sesión firmada.
2. La actividad explícita del usuario renueva `lastActivity` y rota el nonce.
3. Las consultas automáticas a `GET /api/auth/session` validan la sesión, pero no renuevan el tiempo de inactividad.
4. Si pasan más de 60 minutos sin actividad explícita, la sesión vence por `idle_expired`.
5. Aunque el usuario continúe activo, la sesión vence a las 12 horas desde el login por `absolute_expired`.
6. El logout invalida inmediatamente la cookie y devuelve el dashboard al modo demo.

## Motivo del cambio

La política anterior era de 20 minutos de inactividad y 8 horas absolutas. Resultaba demasiado corta para una operatoria normal del dashboard y provocaba cierres frecuentes durante pausas de trabajo.

La nueva política reduce fricción sin convertir la sesión en permanente. El límite de inactividad sigue existiendo y el límite absoluto obliga a autenticarse nuevamente, como máximo, una vez cada 12 horas.

## Validación obligatoria

Toda modificación futura de estos valores debe actualizar simultáneamente:

- `worker/config.mjs`;
- `web/scripts/session-tests.mjs`;
- este documento;
- `CONTEXTO LEADX` en Drive;
- la evidencia del release desplegado.

Antes de desplegar debe pasar:

```bash
npm --prefix web run test:session
npm --prefix web test
npm --prefix web run typecheck
```

Los tests deben demostrar:

- expiración por inactividad después de 60 minutos;
- renovación por actividad explícita;
- polling sin renovación;
- expiración absoluta después de 12 horas aun con actividad;
- eliminación segura del estado real al vencer o cerrar sesión.

## Estado de producción

Estos valores sólo se consideran productivos después de completar el pipeline Workers-first, confirmar el nuevo version ID activo al 100%, validar login/sesión/logout y reconciliar el mismo source SHA en GitHub y Drive.
