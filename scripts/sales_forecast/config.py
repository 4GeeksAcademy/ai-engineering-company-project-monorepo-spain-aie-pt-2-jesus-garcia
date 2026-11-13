"""Constantes y configuración del modelo de pronóstico de ventas.

Todos los valores que afectan a la reproducibilidad del experimento viven aquí.
La semilla es única y se propaga a ``RandomForestRegressor`` y a cualquier
muestreo auxiliar.
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Reproducibilidad
# ---------------------------------------------------------------------------
SEED = 42

# ---------------------------------------------------------------------------
# Dataset (ver docs/models-training-rag/sales-forecasting-regression.md)
# ---------------------------------------------------------------------------
TARGET = "revenue_eur"
MARKET = "consolidated"
EXPECTED_COLUMNS = (
    "month",
    "revenue_eur",
    "shipments_processed",
    "avg_revenue_per_shipment_eur",
    "market",
)
NUMERIC_COLUMNS = (
    "revenue_eur",
    "shipments_processed",
    "avg_revenue_per_shipment_eur",
)

# Regla de negocio: 10 años mensuales → primeros 8 de entrenamiento y los 2
# más recientes de test. Con 12 meses por año son 96 y 24 filas.
TRAIN_YEARS = 8
TEST_YEARS = 2
MONTHS_PER_YEAR = 12

# ---------------------------------------------------------------------------
# Features causales
# ---------------------------------------------------------------------------
# El target que aprende el bosque es el crecimiento interanual logarítmico
# ``log(revenue_t) - log(revenue_{t-12})``. Es una serie estacionaria, así que
# el modelo no necesita extrapolar niveles fuera del rango de entrenamiento
# (limitación clásica de los árboles). El pronóstico final de ``revenue_eur``
# se reconstruye multiplicando por el ingreso del mismo mes del año anterior,
# que sí se conoce en el momento de predecir.
#
# Solo se usan valores pasados (``shift`` positivo o ventanas cerradas en t-1)
# más calendario del mes objetivo.
FEATURE_COLUMNS = (
    "month_sin",
    "month_cos",
    "is_peak_season",
    "is_february_dip",
    "yoy_growth_lag_1",
    "yoy_growth_lag_2",
    "yoy_growth_lag_3",
    "yoy_growth_lag_12",
    "yoy_rolling_mean_3",
    "yoy_rolling_mean_6",
)

# ---------------------------------------------------------------------------
# Modelo
# ---------------------------------------------------------------------------
# Justificación (ver README):
# - Solo hay 72 filas útiles de entrenamiento: el target de crecimiento necesita
#   12 meses de historia y sus lags otros 12. En ese régimen de datos pequeños
#   un boosting profundo sobreajusta y exige ajuste fino; un bosque aleatorio
#   con hojas mínimas de 3 muestras es más estable.
# - El CEO y Operaciones necesitan explicabilidad: ``feature_importances_``
#   traduce el modelo a "pesa más el crecimiento del año pasado y el mes".
# - El ajuste es cuestión de segundos (sin GPU), lo que permite reentrenar.
# - La dispersión de las predicciones de los 500 árboles da una banda de
#   variabilidad empírica sin supuestos paramétricos.
N_ESTIMATORS = 500
MIN_SAMPLES_LEAF = 3
MAX_FEATURES = 0.7
# ``n_jobs=1`` para que el entrenamiento sea bit a bit reproducible: la suma
# en paralelo de las predicciones de los árboles puede alterar los últimos
# decimales. El dataset es diminuto y el coste es despreciable.
N_JOBS = 1

# El target que aprende el modelo es el crecimiento interanual logarítmico
# (estacionario). El pronóstico final se expresa en ``revenue_eur``.
GROWTH_TARGET_COLUMN = "yoy_log_growth"
BASE_LAG_MONTHS = 12

# Cuantiles de la banda de variabilidad (dispersión entre árboles).
INTERVAL_QUANTILES = (0.10, 0.90)
OUTER_INTERVAL_QUANTILES = (0.05, 0.95)

# ---------------------------------------------------------------------------
# Métricas
# ---------------------------------------------------------------------------
# El test tiene solo 24 meses: 5 bins dejan ~5 observaciones por bin y evitan
# que un bin vacío infle artificialmente el PSI.
PSI_BINS = 5
PSI_STABLE_THRESHOLD = 0.10
PSI_MODERATE_THRESHOLD = 0.25
K2_BINS = 4

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_PATH = PROJECT_ROOT / "data" / "raw" / "trackflow_sales.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "docs" / "models-training-rag"
FIGURE_FILENAME = "sales_forecast_test_2024_2025.png"
PREDICTIONS_FILENAME = "predictions_test.csv"
METRICS_FILENAME = "metrics.json"

# ---------------------------------------------------------------------------
# Evaluación temporal (docs/models-training-rag/evaluating-regression-model.md)
# ---------------------------------------------------------------------------
# La CV se hace solo sobre el set de entrenamiento (96 meses), y en la práctica
# sobre las 72 filas con features completas (2018-01 → 2023-12). Seis folds de
# 8 meses garantizan al menos 5 folds y que todos tengan >= 2 años de historia;
# con 5 folds de 12 meses el primero tendría solo 12 filas (arranque en frío).
CV_N_SPLITS = 6
CV_TEST_MONTHS = 8
CV_GAP_MONTHS = 0

# Curva de aprendizaje: validación fija en el último año del train (2023) y
# ventana de entrenamiento que crece hacia atrás desde 2022-12. Así cada punto
# respeta el orden temporal y se mide el efecto de añadir historia, no de
# mezclar filas al azar.
LEARNING_CURVE_VALIDATION_MONTHS = 12
LEARNING_CURVE_TRAIN_SIZES = (24, 30, 36, 42, 48, 54, 60)

# Acción correctiva propuesta en el informe: reducir la varianza del bosque
# subiendo el tamaño mínimo de hoja. Se evalúa en los mismos folds, sin tocar
# el modelo que produce los artefactos 2024-2025.
REGULARIZED_MIN_SAMPLES_LEAF = 5

EVAL_OUTPUT_DIR = PROJECT_ROOT / "data" / "eval"
LEARNING_CURVE_FILENAME = "learning_curve.png"
CV_RESULTS_FILENAME = "cv_results.json"
CV_FOLDS_FILENAME = "cv_folds.csv"
LEARNING_CURVE_CSV_FILENAME = "learning_curve.csv"
