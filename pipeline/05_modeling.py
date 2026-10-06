"""
FASE 5 - Modelado multivariado (leak-free) de recompra a 18 meses.

Poblacion: eligible_18m = True (cohortes maduras) y con datos de trip1 validos
(n_transacciones_trip1 IS NOT NULL). Target: rebuy_18m (estandar a pedido de
Matias, 2026-09-21 -- antes se usaba 12m).

Features: SOLO Grupo A del diccionario de variables (ver variable_dictionary.py).
Explicitamente NO se usan: cantidad_visitas/searches_entre_trips, flg_app_entre_trips,
variables de trip2, flg_mismo_producto, ni Customer Service (sin timestamp de la
interaccion, no se puede garantizar que sea anterior al target). Tampoco se usan
eventos_*/first-last click en el modelo principal: su cobertura es 0% antes de 2021
(ver auditoria), lo que los volveria un proxy casi perfecto de "cohorte reciente"
en vez de una señal real de comportamiento -> alto riesgo de confusion aun
controlando por cohort_year. Se deja como analisis secundario restringido a
cohortes 2021+ (ver seccion final de este script).

Split temporal (out-of-time, NO random): train = cohortes con fecha_primer_trip
antes de 2024-08 (~80%), test = cohortes 2024-08 en adelante hasta la ultima
cohorte madura (~20%). Evita fugas de informacion temporal entre train y test.

Modelos:
  - Logistic Regression (statsmodels) sobre muestra -> coeficientes, odds ratios, IC95%.
  - HistGradientBoostingClassifier (sklearn) con soporte nativo de categoricas ->
    metricas no lineales + SHAP para importancia/interpretabilidad.

Metricas: ROC-AUC, PR-AUC, calibracion (bins), tasa de recompra observada por
decil de score (lift table). Todo calculado SOLO sobre el test set (out-of-time).
"""
import json
import time
import warnings
from pathlib import Path

import duckdb
import joblib
import numpy as np
import pandas as pd
import shap
import statsmodels.api as sm
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, roc_auc_score, roc_curve
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

CACHE_DIR = Path(r"E:\Soporte\Reporting\Rebuy\_cache_v2")
MODELING_PARQUET = CACHE_DIR / "modeling_view.parquet"
MODEL_PATH = CACHE_DIR / "gbm_rebuy_18m.joblib"
PROJECT_DIR = Path(__file__).resolve().parent.parent
OUT_JSON = PROJECT_DIR / "pipeline" / "_fragment_modeling.json"

CUTOFF_MONTH = "2024-08"
CAT_FEATURES = ["pais", "purchase_type", "plataforma_principal", "canal_principal",
                 "flight_class_simple", "cohort_year", "tipo_viaje", "rango_edad_primer_trip",
                 "income", "bucket_anticipacion_compra", "bucket_duracion_viaje"]
BIN_FEATURES = ["flg_uso_cupon", "flg_uso_puntos", "flg_tarjeta_credito", "flg_transferencia",
                 "flg_deposito_bancario", "flg_cash", "flg_multi_instrumento_pago",
                 "flg_multi_tipo_pago", "flg_app_90d_antes_trip1", "tiene_vuelo"]
NUM_FEATURES = ["log_gross_bookings", "visitas_app_90d_antes_trip1", "n_transacciones_trip1",
                 "antiguedad_usuario_dias_al_trip1"]
TARGET = "rebuy_18m"  # estandar a pedido de Matias (2026-09-21), antes rebuy_12m
ELIGIBLE = "eligible_18m"


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def simplify_multivalue(s, keep_n=1):
    if s is None:
        return None
    parts = str(s).split(" | ")
    return parts[0] if parts else None


def load_data(sample_train=1_500_000, seed=42):
    con = duckdb.connect()
    con.execute("PRAGMA disable_progress_bar")
    con.execute("PRAGMA memory_limit='40GB'")
    q = f"""
        SELECT
            pais, purchase_type, plataforma_trip_1, canales_compra_trip_1, flight_class,
            cohort_year, cohort_month,
            flg_uso_cupon, flg_uso_puntos, flg_tarjeta_credito, flg_transferencia,
            flg_deposito_bancario, flg_cash, flg_multi_instrumento_pago, flg_multi_tipo_pago,
            flg_app_90d_antes_trip1, tiene_vuelo,
            tipo_viaje, rango_edad_primer_trip, income,
            bucket_anticipacion_compra, bucket_duracion_viaje, antiguedad_usuario_dias_al_trip1,
            gross_bookings_usd, visitas_app_90d_antes_trip1, n_transacciones_trip1,
            {TARGET}
        FROM read_parquet('{MODELING_PARQUET}')
        WHERE {ELIGIBLE} AND n_transacciones_trip1 IS NOT NULL
    """
    df = con.execute(q).fetchdf()
    df["plataforma_principal"] = df["plataforma_trip_1"].apply(simplify_multivalue)
    df["canal_principal"] = df["canales_compra_trip_1"].apply(simplify_multivalue)
    df["flight_class_simple"] = df["flight_class"].apply(
        lambda s: "Sin vuelo" if s is None else (simplify_multivalue(s) or "Otro"))
    df["log_gross_bookings"] = np.log1p(df["gross_bookings_usd"].clip(lower=0).fillna(0))
    df["visitas_app_90d_antes_trip1"] = df["visitas_app_90d_antes_trip1"].fillna(0)
    df["antiguedad_usuario_dias_al_trip1"] = df["antiguedad_usuario_dias_al_trip1"].fillna(
        df["antiguedad_usuario_dias_al_trip1"].median())
    for c in ["tipo_viaje", "rango_edad_primer_trip", "income", "bucket_anticipacion_compra", "bucket_duracion_viaje"]:
        df[c] = df[c].fillna("Sin dato")
    for b in BIN_FEATURES:
        df[b] = df[b].fillna(0).astype(int)
    df[TARGET] = df[TARGET].astype(int)

    # Categorias muy chicas (<1000 usuarios en todo el dataset elegible) se agrupan en
    # "Otros": con pocas decenas/cientos de casos, un one-hot individual puede generar
    # cuasi-separacion perfecta (todas las filas de esa categoria con el mismo target) y
    # una matriz singular en la logistica. No aporta senal confiable de todas formas.
    for c in ["pais", "purchase_type", "plataforma_principal", "canal_principal", "flight_class_simple",
              "tipo_viaje", "rango_edad_primer_trip", "income", "bucket_anticipacion_compra", "bucket_duracion_viaje"]:
        vc = df[c].value_counts()
        rare = vc[vc < 1000].index
        df[c] = df[c].where(~df[c].isin(rare), other="Otros")

    is_train = df["cohort_month"] < CUTOFF_MONTH
    train_df = df[is_train].copy()
    test_df = df[~is_train].copy()
    log(f"train={len(train_df):,}  test={len(test_df):,}  (corte temporal: {CUTOFF_MONTH})")

    if sample_train and len(train_df) > sample_train:
        train_df = train_df.sample(n=sample_train, random_state=seed)
        log(f"submuestra de train para acotar tiempo de entrenamiento: {len(train_df):,}")

    return train_df, test_df


def build_matrix(df, ref_columns=None):
    X = pd.get_dummies(df[CAT_FEATURES], drop_first=True)
    for b in BIN_FEATURES:
        X[b] = df[b].values
    for n in NUM_FEATURES:
        X[n] = df[n].values
    if ref_columns is not None:
        X = X.reindex(columns=ref_columns, fill_value=0)
    return X


def fit_logistic(train_df, n_boot=100, boot_size=150_000):
    """
    Regresion logistica con regularizacion L2 leve (sklearn, siempre converge y es
    robusta a la cuasi-separacion de categorias chicas) para el punto estimado, y
    bootstrap para el intervalo de confianza de cada odds ratio. Se prefiere esto
    sobre statsmodels.Logit puro porque con ~40 columnas dummy y categorias de baja
    frecuencia (paises chicos, tiers de vuelo raros) el Hessiano de la maxima
    verosimilitud sin penalizar resulta numericamente singular.
    """
    from sklearn.linear_model import LogisticRegression

    log("Ajustando regresion logistica (sklearn, L2) + bootstrap para IC95%...")
    sample = train_df.sample(n=min(600_000, len(train_df)), random_state=42)
    X_full = build_matrix(sample)
    columns = list(X_full.columns)
    num_cols = [c for c in NUM_FEATURES if c in X_full.columns]

    def fit_once(df_sub):
        X = build_matrix(df_sub, ref_columns=columns)
        scaler = StandardScaler()
        X_scaled = X.copy()
        X_scaled[num_cols] = scaler.fit_transform(X[num_cols])
        y = df_sub[TARGET].values
        clf = LogisticRegression(penalty="l2", C=1.0, max_iter=2000, solver="lbfgs")
        clf.fit(X_scaled.values, y)
        return clf.coef_[0], clf.intercept_[0], scaler

    log("  fit puntual...")
    coef_point, intercept_point, scaler = fit_once(sample)

    log(f"  bootstrap ({n_boot} iteraciones de {boot_size:,} filas)...")
    boot_coefs = np.zeros((n_boot, len(columns)))
    for i in range(n_boot):
        boot_sample = train_df.sample(n=min(boot_size, len(train_df)), random_state=1000 + i)
        c, _, _ = fit_once(boot_sample)
        boot_coefs[i, :] = c

    ci_low = np.percentile(boot_coefs, 2.5, axis=0)
    ci_high = np.percentile(boot_coefs, 97.5, axis=0)
    # p-value aproximado (dos colas) a partir de la fraccion de bootstrap que cruza 0
    p_approx = 2 * np.minimum((boot_coefs > 0).mean(axis=0), (boot_coefs < 0).mean(axis=0))
    p_approx = np.clip(p_approx, 1.0 / n_boot, 1.0)

    table = pd.DataFrame({
        "feature": columns,
        "coef": coef_point,
        "or": np.exp(coef_point),
        "or_low": np.exp(ci_low),
        "or_high": np.exp(ci_high),
        "p_value": p_approx,
    }).sort_values("or", ascending=False)
    log(f"Logistic listo. Top OR: {table.iloc[0]['feature']}={table.iloc[0]['or']:.2f}")
    return table, columns, scaler, num_cols, float(intercept_point)


def evaluate(y_true, y_prob):
    auc = roc_auc_score(y_true, y_prob)
    pr_auc = average_precision_score(y_true, y_prob)
    fpr, tpr, _ = roc_curve(y_true, y_prob)
    roc_points = list(zip(fpr[::max(1, len(fpr)//200)].tolist(), tpr[::max(1, len(fpr)//200)].tolist()))

    df = pd.DataFrame({"y": y_true, "p": y_prob})
    df["decile"] = pd.qcut(df["p"].rank(method="first"), 10, labels=False)
    decile_table = df.groupby("decile").agg(n=("y", "size"), rate=("y", "mean"), avg_score=("p", "mean")).reset_index()
    decile_table = decile_table.sort_values("decile", ascending=False)
    base_rate = df["y"].mean()

    bins = pd.cut(df["p"], bins=np.linspace(0, 1, 11), include_lowest=True)
    calib = df.groupby(bins, observed=False).agg(n=("y", "size"), obs_rate=("y", "mean"), avg_pred=("p", "mean")).reset_index(drop=True)
    calib = calib[calib["n"] > 0]

    return {
        "roc_auc": float(auc), "pr_auc": float(pr_auc), "base_rate": float(base_rate),
        "roc_curve_sample": roc_points,
        "decile_table": decile_table.to_dict(orient="records"),
        "calibration": calib.to_dict(orient="records"),
    }


def main():
    train_df, test_df = load_data()

    logit_table, logit_columns, scaler, num_cols, const_val = fit_logistic(train_df)

    log("Entrenando HistGradientBoostingClassifier...")
    gbm_sample = train_df if len(train_df) <= 2_000_000 else train_df.sample(2_000_000, random_state=42)
    for c in CAT_FEATURES:
        gbm_sample[c] = gbm_sample[c].astype("category")
        test_df[c] = pd.Categorical(test_df[c], categories=gbm_sample[c].cat.categories)
    feat_cols = CAT_FEATURES + BIN_FEATURES + NUM_FEATURES
    for n in NUM_FEATURES:
        gbm_sample[n] = gbm_sample[n].astype(float)
        test_df[n] = test_df[n].astype(float)
    X_train = gbm_sample[feat_cols]
    y_train = gbm_sample[TARGET]
    gbm = HistGradientBoostingClassifier(
        categorical_features=[c in CAT_FEATURES for c in feat_cols],
        max_depth=6, max_iter=200, learning_rate=0.08, random_state=42,
        early_stopping=True, validation_fraction=0.1,
    )
    gbm.fit(X_train, y_train)
    log(f"GBM entrenado con {len(X_train):,} filas, {gbm.n_iter_} iteraciones")

    X_test_gbm = test_df[feat_cols]
    y_test = test_df[TARGET].values
    p_gbm = gbm.predict_proba(X_test_gbm)[:, 1]
    metrics_gbm = evaluate(y_test, p_gbm)
    log(f"GBM  ROC-AUC={metrics_gbm['roc_auc']:.4f}  PR-AUC={metrics_gbm['pr_auc']:.4f}")

    X_test_logit = build_matrix(test_df, ref_columns=logit_columns)
    X_test_logit_scaled = X_test_logit.copy()
    X_test_logit_scaled[num_cols] = scaler.transform(X_test_logit[num_cols])
    beta = pd.Series(0.0, index=logit_columns)
    for _, row in logit_table.iterrows():
        beta[row["feature"]] = row["coef"]
    lin = const_val + X_test_logit_scaled[logit_columns].values.astype(float) @ beta[logit_columns].values.astype(float)
    p_logit = 1 / (1 + np.exp(-lin))
    metrics_logit = evaluate(y_test, p_logit)
    log(f"Logit ROC-AUC={metrics_logit['roc_auc']:.4f}  PR-AUC={metrics_logit['pr_auc']:.4f}")

    log("Calculando permutation importance sobre muestra del test set...")
    # Nota metodologica: se intento usar SHAP (TreeExplainer) pero la version instalada
    # no soporta el manejo nativo de categoricas de HistGradientBoostingClassifier
    # (intenta castear todo a float). Permutation importance es una alternativa valida
    # y model-agnostic: mide cuanto empeora el ROC-AUC al mezclar aleatoriamente cada
    # columna, manteniendo todo lo demas igual.
    from sklearn.inspection import permutation_importance
    perm_sample_idx = X_test_gbm.sample(n=min(50_000, len(X_test_gbm)), random_state=42).index
    perm_result = permutation_importance(
        gbm, X_test_gbm.loc[perm_sample_idx], test_df.loc[perm_sample_idx, TARGET],
        scoring="roc_auc", n_repeats=5, random_state=42, n_jobs=-1,
    )
    mean_abs_shap = pd.Series(perm_result.importances_mean, index=feat_cols).clip(lower=0).sort_values(ascending=False)

    pdp_rows = {}
    from sklearn.inspection import partial_dependence
    X_pdp = X_train.sample(n=min(100_000, len(X_train)), random_state=42)
    for feat in ["visitas_app_90d_antes_trip1"]:
        pd_res = partial_dependence(gbm, X_pdp, [feat], kind="average", grid_resolution=30,
                                     response_method="predict_proba", method="brute")
        pdp_rows[feat] = {"grid": pd_res["grid_values"][0].tolist(), "avg_pred": pd_res["average"][0].tolist()}

    out = {
        "poblacion": {"n_train": int(len(train_df)), "n_test": int(len(test_df)),
                      "cutoff_month": CUTOFF_MONTH, "base_rate_test": float(y_test.mean())},
        "features_usadas": feat_cols,
        "logistic": {
            "table": logit_table.to_dict(orient="records"),
            "metrics": metrics_logit,
        },
        "gbm": {
            "metrics": metrics_gbm,
            "permutation_importance": [{"feature": k, "importance": float(v)} for k, v in mean_abs_shap.items()],
            "partial_dependence": pdp_rows,
        },
    }

    def npconv(o):
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return None if np.isnan(o) else float(o)
        if isinstance(o, (np.bool_,)):
            return bool(o)
        if pd.isna(o):
            return None
        return str(o)

    OUT_JSON.write_text(json.dumps(out, default=npconv, ensure_ascii=False), encoding="utf-8")
    log(f"Guardado {OUT_JSON} ({OUT_JSON.stat().st_size/1024:.1f} KB)")

    # Guardar modelo para scoring en 08_score_audience.py
    cat_levels = {c: list(gbm_sample[c].cat.categories) for c in CAT_FEATURES}
    joblib.dump({
        "model": gbm,
        "feat_cols": feat_cols,
        "cat_features": CAT_FEATURES,
        "bin_features": BIN_FEATURES,
        "num_features": NUM_FEATURES,
        "cat_levels": cat_levels,
        "importance": {k: float(v) for k, v in mean_abs_shap.items()},
    }, MODEL_PATH)
    log(f"GBM guardado en {MODEL_PATH} ({MODEL_PATH.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
