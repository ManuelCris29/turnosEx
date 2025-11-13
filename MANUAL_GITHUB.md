# 📚 MANUAL DE GITHUB - SUBIR CAMBIOS AL REPOSITORIO
## Guía Completa para Gestionar tu Código en GitHub

**Última actualización:** 2025-11-11  
**Proyecto:** AppTurnos - Sistema de Gestión de Cambios de Turno

---

## 📋 TABLA DE CONTENIDOS

1. [Configuración Inicial](#configuración-inicial)
2. [Flujo de Trabajo Diario](#flujo-de-trabajo-diario)
3. [Comandos Git Esenciales](#comandos-git-esenciales)
4. [Buenas Prácticas](#buenas-prácticas)
5. [Resolución de Problemas](#resolución-de-problemas)
6. [Comandos Rápidos](#comandos-rápidos)

---

## ⚙️ CONFIGURACIÓN INICIAL

### **Paso 1: Verificar que Git está instalado**

```bash
git --version
```

Si no está instalado, descárgalo desde: https://git-scm.com/downloads

### **Paso 2: Configurar tu identidad (solo la primera vez)**

```bash
git config --global user.name "Tu Nombre"
git config --global user.email "tu.email@ejemplo.com"
```

**Ejemplo:**
```bash
git config --global user.name "Manuel Moreno"
git config --global user.email "manuel.moreno@parqueexplora.org"
```

### **Paso 3: Verificar configuración**

```bash
git config --global --list
```

### **Paso 4: Configurar autocrlf (importante para Windows)**

```bash
git config --global core.autocrlf true
```

Esto evita problemas con saltos de línea entre Windows y Linux.

### **Paso 5: Clonar el repositorio (si es la primera vez)**

```bash
cd C:\appTurnos
git clone https://github.com/tu-usuario/tu-repositorio.git
```

O si ya tienes el repositorio local, verifica la conexión:

```bash
cd C:\appTurnos
git remote -v
```

Si no hay remoto configurado, agrégalo:

```bash
git remote add origin https://github.com/tu-usuario/tu-repositorio.git
```

---

## 🔄 FLUJO DE TRABAJO DIARIO

### **SECUENCIA RECOMENDADA (Paso a Paso)**

#### **1. Verificar Estado Actual**

Antes de hacer cualquier cambio, siempre verifica qué archivos has modificado:

```bash
cd C:\appTurnos
git status
```

**Esto te mostrará:**
- Archivos modificados (en rojo)
- Archivos nuevos sin rastrear (en rojo)
- Archivos listos para commit (en verde)

#### **2. Ver los Cambios Específicos (Opcional pero Recomendado)**

Para ver exactamente qué cambió en cada archivo:

```bash
git diff
```

O para ver cambios en un archivo específico:

```bash
git diff AppTurnosExplora/solicitudes/views.py
```

#### **3. Agregar Archivos al Staging Area**

**Opción A: Agregar todos los archivos modificados**
```bash
git add .
```

**Opción B: Agregar archivos específicos (RECOMENDADO)**
```bash
git add AppTurnosExplora/solicitudes/views.py
git add AppTurnosExplora/solicitudes/services/solicitud_factory.py
```

**Opción C: Agregar por directorio**
```bash
git add AppTurnosExplora/solicitudes/
```

**⚠️ IMPORTANTE:** No agregues archivos que no deban estar en el repositorio:
- `db.sqlite3` (base de datos local)
- `__pycache__/` (caché de Python)
- `*.pyc` (archivos compilados)
- `.env` (variables de entorno)
- `venv/` o `venvturnos/` (entornos virtuales)

#### **4. Verificar lo que se va a Subir**

Antes de hacer commit, verifica qué archivos están en staging:

```bash
git status
```

Los archivos en **verde** son los que se subirán.

#### **5. Crear el Commit (Guardar los Cambios)**

```bash
git commit -m "Descripción clara de los cambios realizados"
```

**Ejemplos de mensajes descriptivos:**
```bash
git commit -m "Agregar validación de festivos en CT Permanente"
git commit -m "Corregir bug en aplicar_cambios de CambioTurnoStrategy"
git commit -m "Implementar retorno automático a jornada inicial"
git commit -m "Actualizar documentación de migración AWS"
```

**⚠️ REGLAS PARA MENSAJES DE COMMIT:**
- ✅ Usa español (o inglés si prefieres)
- ✅ Sé descriptivo pero conciso
- ✅ Usa presente: "Agregar" no "Agregué"
- ✅ Primera letra mayúscula
- ✅ No uses punto al final

**Ejemplos BUENOS:**
- ✅ "Agregar validación de límite de cambios por fecha"
- ✅ "Corregir error en cálculo de jornada contraria"
- ✅ "Actualizar template de solicitar_ct_permanente.html"

**Ejemplos MALOS:**
- ❌ "cambios"
- ❌ "fix"
- ❌ "actualización"
- ❌ "corrección de errores varios"

#### **6. Obtener Cambios del Repositorio Remoto (IMPORTANTE)**

**SIEMPRE antes de subir, obtén los últimos cambios:**

```bash
git pull origin main
```

O si tu rama se llama `master`:

```bash
git pull origin master
```

**¿Por qué es importante?**
- Evita conflictos
- Mantiene tu código actualizado
- Previene sobrescribir cambios de otros

**Si hay conflictos:**
- Git te avisará
- Resuelve los conflictos manualmente
- Luego continúa con `git add .` y `git commit`

#### **7. Subir los Cambios a GitHub**

```bash
git push origin main
```

O si tu rama se llama `master`:

```bash
git push origin master
```

**Si es la primera vez que subes:**
```bash
git push -u origin main
```

El flag `-u` establece el tracking de la rama.

#### **8. Verificar que se Subió Correctamente**

Ve a tu repositorio en GitHub y verifica que los cambios aparecen.

---

## 📝 COMANDOS GIT ESENCIALES

### **Comandos de Consulta (No Modifican Nada)**

```bash
# Ver estado del repositorio
git status

# Ver historial de commits
git log

# Ver historial simplificado (una línea por commit)
git log --oneline

# Ver cambios en archivos modificados
git diff

# Ver cambios en archivos en staging
git diff --staged

# Ver información del repositorio remoto
git remote -v

# Ver qué rama estás usando
git branch
```

### **Comandos de Modificación**

```bash
# Agregar archivos al staging
git add .                    # Todos los archivos
git add archivo.py           # Un archivo específico
git add directorio/          # Un directorio completo

# Quitar archivo del staging (sin borrarlo)
git reset HEAD archivo.py

# Crear commit
git commit -m "Mensaje descriptivo"

# Modificar el último commit (si olvidaste algo)
git commit --amend -m "Nuevo mensaje"

# Agregar cambios al último commit
git add archivo_olvidado.py
git commit --amend --no-edit
```

### **Comandos de Sincronización**

```bash
# Obtener cambios del remoto
git pull origin main

# Subir cambios al remoto
git push origin main

# Ver diferencias con el remoto (sin descargar)
git fetch origin
git diff origin/main
```

### **Comandos de Ramas**

```bash
# Ver ramas locales
git branch

# Ver todas las ramas (locales y remotas)
git branch -a

# Crear nueva rama
git branch nombre-rama

# Cambiar de rama
git checkout nombre-rama

# Crear y cambiar a nueva rama
git checkout -b nombre-rama

# Eliminar rama local
git branch -d nombre-rama
```

---

## ✅ BUENAS PRÁCTICAS

### **1. Commit Frecuente**

- ✅ Haz commits pequeños y frecuentes
- ✅ Cada commit debe representar un cambio lógico completo
- ❌ No acumules muchos cambios en un solo commit

**Ejemplo BUENO:**
```bash
git add AppTurnosExplora/solicitudes/views.py
git commit -m "Agregar validación de festivos en CT Permanente"

git add AppTurnosExplora/solicitudes/services/strategies/ct_permanente_strategy.py
git commit -m "Implementar filtrado de festivos en aplicar_cambios"
```

**Ejemplo MALO:**
```bash
git add .
git commit -m "Muchos cambios"
```

### **2. Mensajes Descriptivos**

- ✅ Describe QUÉ cambió y POR QUÉ (si es relevante)
- ✅ Usa presente: "Agregar", "Corregir", "Implementar"
- ❌ No uses mensajes genéricos como "cambios" o "fix"

### **3. Siempre Pull Antes de Push**

```bash
# SIEMPRE hacer esto antes de push
git pull origin main
git push origin main
```

### **4. Revisar Cambios Antes de Commit**

```bash
# Ver qué cambió
git diff

# Ver qué se va a commitear
git status
git diff --staged
```

### **5. No Subir Archivos Sensibles**

**NUNCA agregues:**
- Contraseñas
- Claves de API
- Archivos `.env` con credenciales
- Base de datos locales (`db.sqlite3`)
- Archivos de configuración personal

**Usa `.gitignore` para excluirlos automáticamente.**

### **6. Mantener el Repositorio Limpio**

```bash
# Ver archivos sin rastrear
git status

# Si hay archivos que no quieres rastrear, agrégalos a .gitignore
```

---

## 🔧 RESOLUCIÓN DE PROBLEMAS

### **Problema 1: "Your branch is ahead of 'origin/main' by X commits"**

**Causa:** Tienes commits locales que no se han subido.

**Solución:**
```bash
git push origin main
```

### **Problema 2: "Your branch is behind 'origin/main' by X commits"**

**Causa:** El repositorio remoto tiene cambios que no tienes localmente.

**Solución:**
```bash
git pull origin main
```

### **Problema 3: "Merge conflict"**

**Causa:** Tú y otra persona modificaron el mismo archivo en las mismas líneas.

**Solución:**
1. Git marca los conflictos en el archivo con:
   ```
   <<<<<<< HEAD
   Tu código
   =======
   Código del remoto
   >>>>>>> origin/main
   ```

2. Edita el archivo manualmente y resuelve el conflicto:
   - Elimina las marcas `<<<<<<<`, `=======`, `>>>>>>>`
   - Mantén el código correcto (o combina ambos si es necesario)

3. Guarda el archivo

4. Marca el conflicto como resuelto:
   ```bash
   git add archivo_con_conflicto.py
   git commit -m "Resolver conflicto en archivo_con_conflicto.py"
   ```

5. Continúa con el pull:
   ```bash
   git pull origin main
   ```

### **Problema 4: "Failed to push some refs"**

**Causa:** El remoto tiene cambios que no tienes.

**Solución:**
```bash
# Primero obtén los cambios
git pull origin main

# Resuelve conflictos si los hay
# Luego vuelve a intentar
git push origin main
```

### **Problema 5: "Changes not staged for commit"**

**Causa:** Modificaste archivos pero no los agregaste al staging.

**Solución:**
```bash
# Agregar archivos modificados
git add .

# O agregar archivos específicos
git add archivo.py

# Luego hacer commit
git commit -m "Descripción de cambios"
```

### **Problema 6: "Nothing to commit, working tree clean"**

**Causa:** No hay cambios para commitear.

**Esto es NORMAL** - significa que todos tus cambios ya están commiteados.

### **Problema 7: Deshacer un Commit (Aún no subido)**

**Si hiciste commit pero NO has hecho push:**

```bash
# Deshacer el último commit (mantiene los cambios)
git reset --soft HEAD~1

# O deshacer y eliminar los cambios
git reset --hard HEAD~1
```

**⚠️ CUIDADO:** `--hard` elimina los cambios permanentemente.

### **Problema 8: Deshacer Cambios en un Archivo**

**Si modificaste un archivo pero NO has hecho commit:**

```bash
# Descartar cambios en un archivo específico
git checkout -- archivo.py

# Descartar TODOS los cambios no commiteados
git checkout -- .
```

**⚠️ CUIDADO:** Esto elimina los cambios permanentemente.

### **Problema 9: Agregaste un Archivo por Error**

**Si agregaste un archivo al staging pero NO has hecho commit:**

```bash
# Quitar del staging (mantiene el archivo)
git reset HEAD archivo.py
```

**Si ya hiciste commit pero NO has hecho push:**

```bash
# Quitar del último commit (mantiene el archivo)
git reset --soft HEAD~1
git reset HEAD archivo.py
git commit -m "Mensaje original"
```

---

## 🚀 COMANDOS RÁPIDOS

### **Secuencia Completa (Copy-Paste Listo)**

```bash
# 1. Ver estado
git status

# 2. Ver cambios
git diff

# 3. Agregar cambios
git add .

# 4. Verificar qué se va a subir
git status

# 5. Crear commit
git commit -m "Descripción de los cambios"

# 6. Obtener cambios del remoto
git pull origin main

# 7. Subir cambios
git push origin main
```

### **Comandos de Una Línea (Para Usuarios Avanzados)**

```bash
# Agregar, commitear y subir (si no hay conflictos)
git add . && git commit -m "Mensaje" && git pull origin main && git push origin main
```

**⚠️ NO RECOMENDADO para principiantes** - Es mejor hacer cada paso por separado.

---

## 📋 CHECKLIST ANTES DE SUBIR

Antes de hacer `git push`, verifica:

- [ ] ✅ Hice `git status` y revisé los archivos
- [ ] ✅ No estoy subiendo archivos sensibles (`.env`, `db.sqlite3`, etc.)
- [ ] ✅ El mensaje del commit es descriptivo
- [ ] ✅ Hice `git pull origin main` para obtener cambios recientes
- [ ] ✅ No hay conflictos pendientes
- [ ] ✅ Los cambios funcionan correctamente (probé localmente)
- [ ] ✅ No hay archivos de prueba o temporales

---

## 🎯 EJEMPLOS DE FLUJOS COMPLETOS

### **Ejemplo 1: Subir Cambios Simples**

```bash
# Cambiaste un archivo: AppTurnosExplora/solicitudes/views.py

# 1. Ver qué cambió
git status
git diff AppTurnosExplora/solicitudes/views.py

# 2. Agregar al staging
git add AppTurnosExplora/solicitudes/views.py

# 3. Crear commit
git commit -m "Corregir validación de fecha en SolicitarCambioTurnoView"

# 4. Obtener cambios del remoto
git pull origin main

# 5. Subir cambios
git push origin main
```

### **Ejemplo 2: Subir Múltiples Archivos Relacionados**

```bash
# Cambiaste varios archivos relacionados con CT Permanente

# 1. Ver estado
git status

# 2. Agregar archivos específicos
git add AppTurnosExplora/solicitudes/services/strategies/ct_permanente_strategy.py
git add AppTurnosExplora/solicitudes/services/solicitud_validator.py
git add AppTurnosExplora/templates/solicitudes/solicitar_ct_permanente.html

# 3. Verificar
git status

# 4. Crear commit
git commit -m "Implementar validación de festivos en CT Permanente"

# 5. Pull y push
git pull origin main
git push origin main
```

### **Ejemplo 3: Subir Documentación**

```bash
# Agregaste un nuevo documento de análisis

# 1. Agregar documento
git add ANALISIS_MIGRACION_AWS.md

# 2. Commit
git commit -m "Agregar análisis de migración a AWS"

# 3. Pull y push
git pull origin main
git push origin main
```

### **Ejemplo 4: Resolver Conflictos**

```bash
# Intentas hacer pull y hay conflictos

# 1. Pull (detecta conflictos)
git pull origin main
# Output: "Auto-merging archivo.py"
# Output: "CONFLICT (content): Merge conflict in archivo.py"

# 2. Abrir archivo.py y resolver conflictos manualmente
# Buscar: <<<<<<< HEAD
# Resolver y eliminar las marcas

# 3. Marcar como resuelto
git add archivo.py

# 4. Completar el merge
git commit -m "Resolver conflicto en archivo.py"

# 5. Subir cambios
git push origin main
```

---

## 🔐 CONFIGURACIÓN DE SEGURIDAD

### **Autenticación con GitHub**

**Opción 1: Personal Access Token (Recomendado)**

1. Ve a GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Genera un nuevo token con permisos `repo`
3. Usa el token como contraseña cuando Git te la pida

**Opción 2: SSH Keys**

```bash
# Generar clave SSH
ssh-keygen -t ed25519 -C "tu.email@ejemplo.com"

# Copiar clave pública
cat ~/.ssh/id_ed25519.pub

# Agregar a GitHub: Settings → SSH and GPG keys → New SSH key
```

---

## 📚 RECURSOS ADICIONALES

### **Documentación Oficial**
- Git: https://git-scm.com/doc
- GitHub: https://docs.github.com

### **Guías Visuales**
- GitHub Guides: https://guides.github.com
- Atlassian Git Tutorial: https://www.atlassian.com/git/tutorials

### **Comandos de Ayuda**

```bash
# Ayuda de cualquier comando
git help comando
git help status
git help commit
git help push
```

---

## ✅ RESUMEN: FLUJO DIARIO RECOMENDADO

```bash
# 1. Ver qué cambió
git status

# 2. (Opcional) Ver cambios específicos
git diff

# 3. Agregar archivos
git add .

# 4. Verificar qué se va a subir
git status

# 5. Crear commit con mensaje descriptivo
git commit -m "Descripción clara de los cambios"

# 6. Obtener cambios del remoto (IMPORTANTE)
git pull origin main

# 7. Subir cambios
git push origin main

# 8. Verificar en GitHub que se subió correctamente
```

---

## 🆘 COMANDOS DE EMERGENCIA

### **Si Todo Sale Mal y Quieres Empezar de Nuevo**

```bash
# ⚠️ CUIDADO: Esto elimina TODOS los cambios no commiteados
git reset --hard HEAD

# Descartar cambios y volver al último commit
git checkout -- .

# Descartar cambios y obtener última versión del remoto
git fetch origin
git reset --hard origin/main
```

**⚠️ ADVERTENCIA:** Estos comandos eliminan cambios permanentemente. Úsalos solo si estás seguro.

---

## 📝 NOTAS FINALES

1. **Practica primero en un proyecto de prueba** si es tu primera vez con Git
2. **Haz commits frecuentes** - es más fácil resolver problemas con commits pequeños
3. **Siempre revisa `git status`** antes de hacer commit
4. **Nunca subas archivos sensibles** (contraseñas, claves, etc.)
5. **Mantén mensajes de commit descriptivos** - tu yo del futuro te lo agradecerá
6. **Si tienes dudas, pregunta** - es mejor preguntar que romper algo

---

**¡Éxito con tu proyecto! 🚀**

**Última actualización:** 2025-11-11

