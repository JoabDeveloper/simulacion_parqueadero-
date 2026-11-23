"""
Generadores de números pseudoaleatorios U ~ Uniforme(0, 1) y pruebas estadísticas.

* GeneradorCongruencial: congruencial multiplicativo de Park–Miller,
      X(i+1) = a · X(i) mod m,   U(i) = X(i) / m,   a = 48271,  m = 2^31 − 1.
  Se calcula por bloques con potencias de a (X(i+j) = a^j · X(i) mod m), lo que da exactamente
  la misma sucesión que la fórmula paso a paso pero mucho más rápido en NumPy.
* GeneradorNumpy: PCG64 de NumPy (alternativa de referencia).

Todas las variables aleatorias del simulador se obtienen de estos U por transformada inversa.
"""
from __future__ import annotations

import math

import numpy as np

M = 2 ** 31 - 1
A = 48271


class GeneradorCongruencial:
    nombre = "Congruencial multiplicativo (Park–Miller)"

    def __init__(self, semilla: int = 12345, bloque: int = 1 << 16):
        self.x = int(semilla) % M or 1
        self.semilla = self.x
        self._pot = np.empty(bloque, dtype=np.int64)
        v = 1
        for j in range(bloque):
            v = (v * A) % M
            self._pot[j] = v
        self._buf = np.empty(0)
        self._pos = 0

    def _rellenar(self):
        xs = (self._pot * np.int64(self.x)) % M      # a^j · X mod m  (producto < 2^62: exacto en int64)
        self.x = int(xs[-1])
        self._buf = xs / M
        self._pos = 0

    def random(self, n: int) -> np.ndarray:
        out = np.empty(int(n))
        i = 0
        while i < n:
            if self._pos >= len(self._buf):
                self._rellenar()
            k = min(n - i, len(self._buf) - self._pos)
            out[i:i + k] = self._buf[self._pos:self._pos + k]
            self._pos += k
            i += k
        return out

    def primeros(self, n: int = 10) -> list[tuple[int, int, float]]:
        """Primeros n pasos de la recurrencia (para mostrar en clase)."""
        x, filas = self.semilla, []
        for i in range(1, n + 1):
            x = (A * x) % M
            filas.append((i, x, x / M))
        return filas


class GeneradorNumpy:
    nombre = "NumPy PCG64"

    def __init__(self, semilla: int = 12345):
        self.rng = np.random.default_rng(int(semilla))

    def random(self, n: int) -> np.ndarray:
        return self.rng.random(int(n))


def crear_generador(tipo: str, semilla: int):
    return GeneradorNumpy(semilla) if tipo.lower().startswith("numpy") else GeneradorCongruencial(semilla)


# ---------------------------------------------------------------------------
# Pruebas de calidad de los números aleatorios
# ---------------------------------------------------------------------------
def chi2_critico(gl: int, alfa: float = 0.05) -> float:
    try:
        from scipy.stats import chi2
        return float(chi2.ppf(1 - alfa, gl))
    except Exception:  # aproximación de Wilson–Hilferty
        z = 1.6448536269514722
        a = 2 / (9 * gl)
        return gl * (1 - a + z * math.sqrt(a)) ** 3


def prueba_uniformidad(u: np.ndarray, k: int = 10) -> dict:
    """H0: los U provienen de Uniforme(0,1). χ² = Σ (FO − FE)² / FE con k − 1 grados de libertad."""
    n = len(u)
    fo = np.histogram(u, bins=k, range=(0, 1))[0]
    fe = n / k
    chi = float(((fo - fe) ** 2 / fe).sum())
    crit = chi2_critico(k - 1)
    return dict(n=n, k=k, fo=fo, fe=fe, chi2=chi, critico=crit, gl=k - 1, acepta=chi < crit)


def prueba_series(u: np.ndarray, m: int = 5) -> dict:
    """
    Prueba de series (independencia): se forman pares consecutivos (U_i, U_i+1), se cuentan en una
    rejilla m × m y se compara con la frecuencia esperada (n − 1) / m². χ² con m² − 1 grados de libertad.
    """
    n = len(u)
    a = np.minimum((u[:-1] * m).astype(int), m - 1)
    b = np.minimum((u[1:] * m).astype(int), m - 1)
    rejilla = np.zeros((m, m), dtype=int)
    np.add.at(rejilla, (a, b), 1)
    fe = (n - 1) / (m * m)
    chi = float(((rejilla - fe) ** 2 / fe).sum())
    crit = chi2_critico(m * m - 1)
    return dict(n=n, m=m, rejilla=rejilla, fe=fe, chi2=chi, critico=crit, gl=m * m - 1, acepta=chi < crit)
