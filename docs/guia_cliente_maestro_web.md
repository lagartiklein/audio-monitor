# Guía: Cliente Maestro Web, Mute Global y EQ 3 Bandas Global

## 1. Concepto de Cliente Maestro Web
- El "cliente maestro web" es un cliente especial que siempre aparece primero en la lista de clientes.
- No depende de qué navegador se conecte primero: el servidor lo expone como un objeto fijo (por ejemplo, id `web_master`).
- Su mixer controla el estado global de la mezcla (mute global, EQ global) que afecta a todos los clientes.

## 2. Estado Global Unificado
- Se introduce un nuevo estado global en el servidor:
  - `global_mutes`: diccionario por canal (ej: `{0: true, 1: false, ...}`) que fuerza mute en todos los clientes.
  - `eq_3band`: parámetros de ecualización por canal (ej: `{0: {low: 0, mid: 0, high: 0}, ...}`).
- Este estado se persiste en disco (archivo dedicado o dentro de `device_registry`).
- Al iniciar, el servidor restaura este estado y lo difunde a todos los clientes.

## 3. API y Broadcasting
- Se agregan nuevos eventos websocket:
  - `update_global_mix`: para que el master web actualice mute/EQ global.
  - `global_mix_state`: broadcast a todos los clientes cuando cambia el estado global.
- El servidor también puede empujar el estado global a clientes nativos (Android) si es necesario.

## 4. Aplicación del Mute Global
- El mute global se aplica en el servidor:
  - Si un canal está muteado globalmente, no se envía (o se envía en silencio) a ningún cliente, sin importar la mezcla local.
  - Esto asegura que el mute es real y consistente para todos.

## 5. EQ 3 Bandas Global
### Opción A: DSP en el Servidor (Recomendado)
- El servidor aplica el EQ 3 bandas a cada canal antes de enviar el audio a los clientes.
- Ventajas: sonido idéntico para todos, control centralizado.
- Requiere más CPU en el servidor.

### Opción B: DSP en Cada Cliente
- El servidor solo guarda y difunde los parámetros de EQ.
- Cada cliente (web, Android) aplica el EQ localmente.
- Menos carga en el servidor, pero puede haber diferencias de sonido entre plataformas.

## 6. UI del Master Web
- El primer item del mixer web es el "cliente maestro".
- Por cada canal, muestra:
  - Botón de mute global (afecta a todos).
  - Controles de EQ 3 bandas (Low, Mid, High).
- El resto de clientes solo pueden controlar su mezcla local.

## 7. Sincronización y Persistencia
- El estado global se guarda en disco y se restaura al iniciar el servidor.
- Cada vez que cambia, se difunde a todos los clientes en tiempo real.
- Los clientes nuevos reciben el estado global al conectarse.

---

### Recomendaciones
- Implementar mute global siempre en el servidor.
- Para EQ, si buscas máxima coherencia, haz el DSP en el servidor.
- Mantén la UI del master simple y clara: mute y EQ por canal, sin controles innecesarios.

---

**Resumen visual:**

```
[Web Master UI] --(update_global_mix)--> [Servidor] --(global_mix_state)--> [Webs, Android]
         |                                 |
         |--(mute/EQ global)               |--(aplica mute/EQ a audio)
         |                                 |--(broadcast estado)
```

