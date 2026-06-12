"""
Split solicitudes/views.py into solicitudes/views/ package (by class names).
Run from AppTurnosExplora: python solicitudes/tools/split_views.py
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "solicitudes" / "views.py"
OUT_DIR = ROOT / "solicitudes" / "views"

HEADER_LINES = 29

# Orden debe coincidir con el orden de aparición en views.py
CLASS_GROUPS: list[tuple[str, list[str]]] = [
    (
        "dashboard_admin.py",
        [
            "SolicitudesView",
            "TipoSolicitudCambioListView",
            "TipoSolicitudCambioCreateView",
            "TipoSolicitudCambioUpdateView",
            "TipoSolicitudCambioDeleteView",
        ],
    ),
    (
        "cambio_turno_pages.py",
        ["CambioTurnoInicioView", "SolicitarCambioTurnoView"],
    ),
    (
        "api_disponibles_ct_preview.py",
        ["ObtenerEmpleadosDisponiblesView", "PrevisualizarCTPermanenteView"],
    ),
    (
        "api_turno_jornada.py",
        [
            "ObtenerTurnoExploradorView",
            "VerificarCoincidenciaJornadasView",
            "ObtenerJornadasRangoView",
            "ObtenerCambioAprobadoView",
        ],
    ),
    ("procesar_solicitud.py", ["ProcesarSolicitudView"]),
    (
        "notificaciones_listas.py",
        [
            "NotificacionesListView",
            "MarcarNotificacionLeidaView",
            "MisSolicitudesListView",
            "SolicitudesPendientesListView",
        ],
    ),
    (
        "aprobacion_views.py",
        [
            "AprobarSolicitudView",
            "AprobarSolicitudReceptorView",
            "RechazarSolicitudView",
            "RechazarSolicitudReceptorView",
            "CancelarSolicitudView",
            "AprobarSolicitudAmbosView",
        ],
    ),
    (
        "aprobacion_email.py",
        [
            "AprobarSolicitudEmailView",
            "RechazarSolicitudEmailView",
            "AprobarSolicitudReceptorEmailView",
            "RechazarSolicitudReceptorEmailView",
        ],
    ),
    (
        "doblada_api.py",
        [
            "ObtenerExploradoresDobladaView",
            "VerificarDobladaExistenteView",
            "ObtenerFechasDescansoView",
        ],
    ),
    ("detalle.py", ["ObtenerDetalleSolicitudView"]),
]


def strip_agent_logs(text: str) -> str:
    pattern = re.compile(
        r"\n?\s*#\s*#region agent log.*?#\s*#endregion",
        re.DOTALL,
    )
    prev = None
    while prev != text:
        prev = text
        text = pattern.sub("", text)
    return text


def find_class_spans(lines: list[str]) -> dict[str, tuple[int, int]]:
    """Nombre de clase -> (start_idx inclusive, end_idx exclusive); incluye @decoradores sobre la clase."""
    class_pat = re.compile(r"^class (\w+)\b")
    starts: list[tuple[int, str]] = []
    for i, ln in enumerate(lines):
        m = class_pat.match(ln)
        if m:
            starts.append((i, m.group(1)))
    spans: dict[str, tuple[int, int]] = {}
    for j, (idx, name) in enumerate(starts):
        real_start = idx
        k = idx - 1
        while k >= 0:
            s = lines[k].strip()
            if s == "" or s.startswith("#"):
                k -= 1
                continue
            if s.startswith("@"):
                real_start = k
                k -= 1
                continue
            break
        end = starts[j + 1][0] if j + 1 < len(starts) else len(lines)
        spans[name] = (real_start, end)
    return spans


def main() -> None:
    raw = strip_agent_logs(SRC.read_text(encoding="utf-8"))
    lines = raw.splitlines(keepends=True)
    header = "".join(lines[:HEADER_LINES])

    preamble_start = HEADER_LINES
    first_class = None
    for i in range(HEADER_LINES, len(lines)):
        if re.match(r"^class \w+", lines[i]):
            first_class = i
            break
    if first_class is None:
        raise SystemExit("No classes found")
    preamble = "".join(lines[preamble_start:first_class])

    spans = find_class_spans(lines)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    exports: list[str] = []

    for fname, class_names in CLASS_GROUPS:
        parts: list[str] = []
        if fname == "dashboard_admin.py":
            parts.append(preamble)
        for cn in class_names:
            if cn not in spans:
                raise SystemExit(f"Class {cn!r} not found in views.py")
            a, b = spans[cn]
            parts.append("".join(lines[a:b]))
            exports.append(cn)
        body = "".join(parts)
        if not body.strip():
            raise SystemExit(f"Empty body for {fname}")
        full = header + "\n" + body
        full = full.replace("from .models ", "from ..models ")
        full = full.replace("from .services.", "from ..services.")
        (OUT_DIR / fname).write_text(full, encoding="utf-8")

    init_lines = [
        '"""Vistas de la app solicitudes (divididas por ámbito)."""',
        "",
    ]
    for fname, _ in CLASS_GROUPS:
        mod = fname[:-3]
        init_lines.append(f"from .{mod} import *  # noqa: F401,F403")
    init_lines.append("")
    init_lines.append("__all__ = [")
    for name in exports:
        init_lines.append(f'    "{name}",')
    init_lines.append("]")
    init_lines.append("")
    (OUT_DIR / "__init__.py").write_text("\n".join(init_lines), encoding="utf-8")
    print("OK:", len(exports), "classes ->", OUT_DIR)


if __name__ == "__main__":
    main()
