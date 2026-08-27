# Imágenes de autenticación (login / registro)

Imágenes usadas por las pantallas de acceso.

## bannerAuth.jpg

Banner del panel lateral izquierdo del login (layout *split-screen*).

- **Nombre exacto:** `bannerAuth.jpg` *(presente en el repo)*
- **Ruta:** `static/img/auth/bannerAuth.jpg`
- **Referenciado desde:** `static/css/auth.css` → `.auth-visual__img`
- **Plantilla:** `core/login/template/login.html`
- **Recomendado:** orientación horizontal, mínimo 1200 px de ancho. Encima lleva un
  degradado semitransparente (`.auth-visual__overlay`), así que una imagen con mucho
  detalle fino se pierde.

Si el archivo faltara, `.auth-visual` deja ver su degradado de respaldo
(azul `#667eea` → morado `#764ba2`) y el login no se rompe visualmente.

> Tras reemplazar la imagen, recuerda `collectstatic` en producción.
