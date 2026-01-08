# 📜 Políticas, Licencia y Términos de Uso

Políticas, términos de servicio y licencia de Fichatech Audio Monitor.

---

## 📋 Tabla de Contenidos

- [Información de Licencia](#información-de-licencia)
- [Términos de Uso](#términos-de-uso)
- [Política de Privacidad](#política-de-privacidad)
- [Política de Datos](#política-de-datos)
- [Responsabilidades](#responsabilidades)
- [Renuncia de Garantías](#renuncia-de-garantías)
- [Limitación de Responsabilidad](#limitación-de-responsabilidad)
- [Modificaciones](#modificaciones)

---

## 📄 Información de Licencia

### Licencia Principal

**Fichatech Audio Monitor** está bajo **Licencia MIT Modificada**.

```
Copyright (c) 2025 Fichatech

Se concede permiso, sin restricciones, a cualquier persona que obtenga una copia
de este software y archivos de documentación asociados (el "Software"), para 
utilizar el Software sin restricción, incluyendo sin limitación los derechos de:

- Usar
- Copiar
- Modificar
- Combinar
- Publicar
- Distribuir
- Sublicenciar
- Vender copias del Software

Con las siguientes condiciones:

1. El aviso de copyright anterior y este aviso de permiso se deben incluir en 
   todas las copias o partes substanciales del Software.

2. Las modificaciones deben indicarse claramente como tales.

3. El Software se proporciona "TAL CUAL", sin garantía de ningún tipo.

4. En ningún caso los autores o titulares del copyright serán responsables por 
   reclamaciones, daños u otras responsabilidades.
```

### Licencias de Dependencias

Fichatech Audio Monitor depende de las siguientes librerías open-source:

| Librería | Versión | Licencia | Notas |
|----------|---------|---------|-------|
| **NumPy** | ≥1.21.0 | BSD 3-Clause | Procesamiento de arrays |
| **Sounddevice** | ≥0.4.5 | MIT | Captura de audio |
| **Flask** | ≥2.0.0 | BSD 3-Clause | Framework web |
| **Flask-SocketIO** | ≥5.0.0 | MIT | WebSocket server |
| **Socket.IO** | ≥5.0.0 | MIT | Comunicación real-time |
| **CustomTkinter** | ≥5.0 | MIT | GUI moderna |
| **Pillow** | ≥8.0.0 | PIL/HPND | Procesamiento de imágenes |
| **psutil** | ≥5.0.0 | BSD | Monitoreo de sistema |

### Conformidad

Todas las dependencias son compatibles con la licencia MIT. No hay restricciones comerciales.

---

## ✅ Términos de Uso

### 1. Aceptación de Términos

Al usar Fichatech Audio Monitor, aceptas estos términos. Si no estás de acuerdo, no uses la aplicación.

### 2. Modificación y Distribución

**Permitido:**
- ✅ Modificar el código fuente para uso personal
- ✅ Distribuir versiones modificadas bajo MIT
- ✅ Usar comercialmente sin restricciones
- ✅ Vender productos basados en Fichatech
- ✅ Usar en proyectos propietarios

**Requerido:**
- ℹ️ Incluir aviso de copyright original
- ℹ️ Indicar modificaciones
- ℹ️ Incluir copia de licencia MIT

### 3. Garantía de Autoría

**Debes mantener:**
- Crédito a Fichatech como desarrollador original
- Referencias a licencia MIT
- Cambios claramente marcados como derivados

### 4. Sin Garantía

El software se proporciona "TAL CUAL" sin garantía de:
- Funcionamiento correcto
- Compatibilidad futura
- Libre de errores
- Apto para propósito específico

### 5. Limitaciones

No puedes:
- ❌ Reclamar autoría original de código sin modificar
- ❌ Usar marca "Fichatech" sin permiso expreso
- ❌ Vender garantías que no puedas proporcionar
- ❌ Violar derechos de terceros

---

## 🔐 Política de Privacidad

### 1. Recolección de Datos

#### Datos de Audio

**Captura Local:**
- ✅ El audio se captura **localmente** en tu dispositivo
- ✅ Se procesa **en memoria RAM** (no se persiste a disco de forma permanente)
- ✅ Se transmite solo a clientes conectados en red configurada

**Almacenamiento:**
- Por defecto: Sin almacenamiento persistente
- Opcional: Puedes grabar en carpeta `recordings/` manualmente
- Control total: Tú controlas qué grabar

#### Datos de Dispositivo

La aplicación **NO recolecta**:
- ❌ Información personal
- ❌ Ubicación
- ❌ Identidad de usuario
- ❌ Detalles de hardware (excepto dispositivos de audio)

La aplicación **SÍ registra**:
- ✅ Dispositivos de audio conectados (nombres, canales)
- ✅ Estadísticas de rendimiento (CPU, memoria local)
- ✅ Logs de conexión/desconexión (sin PII)

### 2. Privacidad de Red

#### Transmisión de Datos

- **Dentro de red local:** Todos los datos se transmiten dentro de tu red LAN
- **Sin servidores externos:** No hay comunicación con servidores remotos
- **Control total:** Tú controlas acceso al puerto 5100-5101
- **Encriptación opcional:** Puedes usar VPN/SSL en tu infraestructura

#### Conexiones de Clientes

```
Audio Monitor Server
    │
    ├─→ [Cliente 1] - Red local
    ├─→ [Cliente 2] - Red local
    └─→ [Cliente 3] - Red local

❌ No hay comunicación con Internet
❌ No hay telemetría
❌ No hay análisis de uso
```

### 3. Datos de Configuración

**Almacenados Localmente:**
- `config/channels_state.json` - Estado de canales
- `config/client_states.json` - Estados de clientes
- `config/devices.json` - Dispositivos configurados

**Nunca se envía a:**
- Servicios en la nube
- Servidores remotos
- Terceros

### 4. Derechos de Usuario

Tienes derecho a:
- 📋 Acceso completo a datos almacenados
- 🗑️ Eliminar cualquier dato
- 🔍 Auditar el código fuente
- 🔐 Usar en entorno offline

### 5. Retención de Datos

| Tipo de Dato | Retención | Eliminación |
|---|---|---|
| Estado de canales | Persistente | Manual |
| Logs de conexión | 30 días | Automático |
| Audio en memoria | Realtime | Inmediato |
| Audio grabado | Indefinido | Manual |
| Cache de cliente | Configurable | Automático |

---

## 💾 Política de Datos

### 1. Propiedad de Datos

**Audio grabado es TÚ PROPIEDAD:**
- Todos los audios capturados te pertenecen
- Puedes usarlos libremente
- No hay restricciones de uso

### 2. Backup y Recuperación

**Datos sin protección:**
```
La aplicación NO proporciona:
- Backup automático
- Recuperación de datos borrados
- Sincronización en la nube
- Redundancia de almacenamiento
```

**Responsabilidad:**
```
Es TU responsabilidad:
- Hacer backups regularmente
- Mantener copias de seguridad
- Usar almacenamiento redundante
```

### 3. Configuración Segura

**Configuración Recomendada:**
```
1. Usar en red privada/local
2. Proteger puerto 5100-5101 con firewall
3. No exponer a Internet sin VPN
4. Usar contraseña si se accede remotamente
5. Actualizar regularmente
```

### 4. Cumplimiento de Regulaciones

La aplicación es **agnóstica de regulación**:
- **GDPR**: No recolecta datos personales
- **CCPA**: No recolecta datos de California
- **HIPAA**: Si se usa en contexto médico, implementar medidas adicionales
- **Local**: Cumple regulaciones locales de audio

---

## ⚖️ Responsabilidades

### Responsabilidades del Usuario

**Aceptas ser responsable de:**

1. **Configuración segura**
   - Proteger puertos de red
   - Configurar firewall apropiadamente
   - Limitar acceso a usuarios autorizados

2. **Datos de audio**
   - Cumplir leyes de privacidad
   - Obtener consentimiento si aplica
   - No grabar sin autorización

3. **Actualizaciones**
   - Mantener software actualizado
   - Monitorear cambios de seguridad
   - Implementar parches

4. **Uso legal**
   - No usar para propósitos ilegales
   - Respetar derechos de propiedad intelectual
   - Cumplir leyes locales

### Responsabilidades del Desarrollador

**Fichatech se compromete a:**

1. **Código abierto**
   - Mantener código disponible públicamente
   - Permitir auditoría de seguridad
   - Responder a issues de seguridad

2. **Documentación**
   - Proporcionar documentación técnica
   - Incluir advertencias de seguridad
   - Documentar cambios

3. **Soporte**
   - Responder a reportes de bugs
   - Implementar fixes críticos
   - Mantener repositorio activo

---

## ⚠️ Renuncia de Garantías

**FICHATECH AUDIO MONITOR SE PROPORCIONA "TAL CUAL" SIN GARANTÍA DE NINGÚN TIPO.**

### Sin Garantías Explícitas

El software se proporciona sin garantía respecto a:

```
❌ Que funcione correctamente en todas las condiciones
❌ Compatibilidad con versiones futuras
❌ Ausencia de errores o bugs
❌ Aptitud para un propósito particular
❌ Integración con otros sistemas
❌ Rendimiento específico
❌ Cumplimiento de requisitos específicos
```

### Sin Garantías Implícitas

Quedan excluidas todas las garantías implícitas tales como:

```
❌ Comerciabilidad
❌ Aptitud para un propósito particular
❌ No infracción de derechos
❌ Calidad satisfactoria
```

### Sin Garantía de Soporte

```
❌ No se garantiza soporte técnico
❌ No se garantiza respuesta a issues
❌ No se garantiza corrección de bugs
❌ No se garantiza compatibilidad futura
```

---

## 🛑 Limitación de Responsabilidad

### Limitación de Daños

**EN NINGÚN CASO FICHATECH O DESARROLLADORES SERÁN RESPONSABLES POR:**

1. **Daños Directos**
   - Pérdida de datos
   - Daño a dispositivos
   - Costos de reemplazo

2. **Daños Indirectos**
   - Pérdida de ingresos
   - Pérdida de oportunidades
   - Daños a negocio
   - Daños a reputación

3. **Daños Especiales o Consecuentes**
   - Cualquier daño secundario
   - Daños punitivos
   - Intereses

### Aún Si

Esta limitación aplica **incluso si**:
- Se ha advertido de posibilidad de daños
- Se conoce de posibilidad de daños
- El daño es previsible
- Fichatech fue negligente

### Máxima Responsabilidad

La responsabilidad máxima de Fichatech es:
```
$0 USD (CERO)
```

---

## 🔄 Modificaciones

### Cambios a Términos

- Fichatech puede modificar estos términos en cualquier momento
- Los cambios entran en vigor inmediatamente
- Continuando el uso implica aceptación de cambios
- Se notificará de cambios mayores en página principal

### Cambios a Software

- Fichatech puede modificar, suspender o discontinuar el software
- No hay garantía de compatibilidad hacia atrás
- Las versiones antiguas pueden dejar de funcionar
- Se recomienda mantener backups de versiones funcionales

### Histórico de Versiones

```
Versión 1.0 - Enero 2026
- Lanzamiento inicial
- Protocolos WebSocket y Nativo
- Modo RF con reconexión automática
- GUI de monitoreo
```

---

## 📞 Contacto y Reportes

### Reporte de Problemas

**Para reportar issues de seguridad:**
1. NO abrir issue público
2. Contactar desarrollador directamente
3. Proporcionar detalles técnicos
4. Permitir tiempo para fix

### Reporte de Bugs

**Para reportar bugs normales:**
1. Abrir issue en repositorio
2. Incluir pasos para reproducir
3. Proporcionar logs relevantes
4. Especificar versión de SO y Python

---

## ✍️ Consentimiento

**Al usar Fichatech Audio Monitor, aceptas:**

- [x] Leer y entender estos términos
- [x] Aceptar la licencia MIT
- [x] Asumir responsabilidad por datos
- [x] Entender la renuncia de garantías
- [x] Limitar responsabilidad del desarrollador
- [x] Cumplir leyes aplicables
- [x] Usar responsablemente el software

---

## 📅 Vigencia

**Válido desde:** Enero 2026  
**Última actualización:** Enero 2026  
**Versión:** 1.0

Estos términos son válidos indefinidamente a menos que sean modificados por Fichatech.

---

## 🌐 Traducción

Estos términos están en español. Si hay conflicto con otras traducciones, prevalece la versión en español.

---

## 📋 Apéndice: Casos de Uso Legales

### ✅ Uso Legal Permitido

```
1. Monitoreo de audio local en estudio de grabación
2. Captura de audio para análisis de acústica
3. Monitoreo de entrada de dispositivos para debugging
4. Streaming de audio dentro de red privada
5. Uso educativo y de investigación
6. Integración en productos propios (bajo MIT)
7. Procesamiento de audio en tiempo real
```

### ⚠️ Uso que Requiere Cuidado

```
1. Grabación de conversaciones - obtener consentimiento
2. Transmisión a Internet - asegurar seguridad
3. Uso en aplicación médica - cumplir regulaciones
4. Uso en producción - implementar redundancia
5. Venta de datos - respetar privacidad
```

### ❌ Uso Prohibido

```
1. Escucha encubierta sin consentimiento
2. Grabación ilegal de conversaciones privadas
3. Transmisión de contenido con copyright sin permiso
4. Uso para espionaje o actividades ilegales
5. Violar derechos de terceros
```

---

**Para más información: Ver [README.md](README.md)**

