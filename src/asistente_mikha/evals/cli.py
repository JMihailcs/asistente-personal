from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from asistente_mikha.evals.cases import load_cases
from asistente_mikha.evals.report import cargar_filas, reporte_completo
from asistente_mikha.evals.runner import barrer, modelos_faltantes
from asistente_mikha.evals.variants import VARIANTES

CASOS_POR_DEFECTO = Path("evals/casos")
SALIDA_POR_DEFECTO = Path("evals/resultados/corrida.jsonl")


def _lista(texto: str) -> list[str]:
    return [parte.strip() for parte in texto.split(",") if parte.strip()]


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mikha-eval", description="Arnés de evals de Mikha")
    sub = parser.add_subparsers(dest="comando", required=True)

    correr = sub.add_parser("correr", help="ejecuta un barrido")
    correr.add_argument("--modelos", type=_lista, required=True)
    correr.add_argument("--variantes", type=_lista, default=["baseline"])
    correr.add_argument("--repeticiones", type=int, default=5)
    correr.add_argument("--casos", type=Path, default=CASOS_POR_DEFECTO)
    correr.add_argument("--salida", type=Path, default=SALIDA_POR_DEFECTO)

    reporte = sub.add_parser("reporte", help="agrega un JSONL a una tabla")
    reporte.add_argument("archivo", type=Path)
    reporte.add_argument("--por", choices=["modelo", "variante", "caso"], default="modelo")

    return parser


def _correr(args: argparse.Namespace) -> int:
    desconocidas = [v for v in args.variantes if v not in VARIANTES]
    if desconocidas:
        print(
            f"variantes desconocidas: {', '.join(desconocidas)}. "
            f"Conocidas: {', '.join(VARIANTES)}",
            file=sys.stderr,
        )
        return 1

    casos = load_cases(args.casos)
    if not casos:
        print(f"no hay casos en {args.casos}", file=sys.stderr)
        return 1

    try:
        faltantes = modelos_faltantes(args.modelos)
    except RuntimeError as error:
        # Un traceback crudo no le dice a nadie que hacer, y este es el
        # instrumento con el que vamos a medir fiabilidad.
        print(f"{error}\nLevantalo con 'ollama serve' y volve a intentar.", file=sys.stderr)
        return 1
    if faltantes:
        print(
            f"modelos no descargados en Ollama: {', '.join(faltantes)}. "
            f"Descargalos con 'ollama pull <modelo>' antes de empezar.",
            file=sys.stderr,
        )
        return 1

    total = len(casos) * len(args.modelos) * len(args.variantes) * args.repeticiones
    print(
        f"{total} corridas: {len(casos)} casos x {len(args.modelos)} modelos "
        f"x {len(args.variantes)} variantes x {args.repeticiones} repeticiones"
    )
    asyncio.run(barrer(casos, args.modelos, args.variantes, args.repeticiones, args.salida))
    print(f"listo. Reporte: mikha-eval reporte {args.salida}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    if args.comando == "correr":
        return _correr(args)
    print(reporte_completo(cargar_filas(args.archivo), args.por))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
