import pandas as pd, numpy as np, time, json, pickle, os
from sklearn.model_selection import train_test_split, RandomizedSearchCV
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error, mean_absolute_percentage_error
from xgboost import XGBRegressor

NUMERIC_FEATURES = ["accommodates", "bedrooms", "bathrooms", "beds",
                     "bedrooms_missing", "bathrooms_missing", "beds_missing",
                     "review_scores_rating", "review_scores_rating_missing",
                     "n_amenities", "minimum_nights", "maximum_nights",
                     "availability_365", "host_listings_count", "host_is_superhost", "has_no_real_max_nights",
                     "latitude", "longitude"]

def build_features(d, market, sample_cap=3000, random_state=42):
    d = d.copy()
    if len(d) > sample_cap:
        d = d.sample(sample_cap, random_state=random_state)
    top_room = d["room_type"].value_counts().index.tolist()
    d["room_type_b"] = d["room_type"].where(d["room_type"].isin(top_room), "Other")
    top_prop = d["property_type"].value_counts().nlargest(8).index.tolist()
    d["property_type_b"] = d["property_type"].where(d["property_type"].isin(top_prop), "Other")
    num = d[NUMERIC_FEATURES].copy()
    for c in num.columns:
        num[c] = num[c].fillna(num[c].median() if num[c].notna().any() else 0)
    dummies = pd.get_dummies(d[["room_type_b", "property_type_b"]], drop_first=True)
    X = pd.concat([num.reset_index(drop=True), dummies.reset_index(drop=True)], axis=1)
    y = d["log_price"].reset_index(drop=True)
    price_capped = d["price_capped"].reset_index(drop=True)
    return X, y, price_capped

def adj_r2(r2, n, p):
    if n - p - 1 <= 0:
        return float("nan")
    return 1 - (1 - r2) * (n - 1) / (n - p - 1)

def evaluate(model, X_test, y_test_log, price_test):
    pred_log = model.predict(X_test)
    pred_price = np.expm1(pred_log)
    pred_price = np.clip(pred_price, 0, None)
    r2 = r2_score(y_test_log, pred_log)
    rmse_log = np.sqrt(mean_squared_error(y_test_log, pred_log))
    mae_log = mean_absolute_error(y_test_log, pred_log)
    rmse_price = np.sqrt(mean_squared_error(price_test, pred_price))
    mae_price = mean_absolute_error(price_test, pred_price)
    mape_price = mean_absolute_percentage_error(price_test.clip(lower=1), pred_price.clip(min=1)) if hasattr(price_test, 'clip') else np.nan
    n, p = len(y_test_log), X_test.shape[1]
    return {
        "r2_log": round(float(r2), 4),
        "adj_r2_log": round(float(adj_r2(r2, n, p)), 4),
        "rmse_log": round(float(rmse_log), 4),
        "mae_log": round(float(mae_log), 4),
        "rmse_price": round(float(rmse_price), 2),
        "mae_price": round(float(mae_price), 2),
        "mape_price_pct": round(float(mape_price) * 100, 2),
        "n_test": n, "n_features": p,
    }

PARAM_DISTS = {
    "Ridge": {"alpha": [0.01, 0.1, 0.3, 1.0, 3.0, 10.0, 30.0, 100.0]},
    "RandomForest": {
        "n_estimators": [100, 200, 300, 400],
        "max_depth": [6, 10, 14, 20, None],
        "min_samples_leaf": [1, 2, 4, 8],
        "max_features": ["sqrt", "log2", 0.5, 0.7],
    },
    "XGBoost": {
        "n_estimators": [100, 200, 300, 400],
        "max_depth": [3, 4, 5, 6, 8],
        "learning_rate": [0.02, 0.05, 0.08, 0.1, 0.15],
        "subsample": [0.6, 0.8, 1.0],
        "colsample_bytree": [0.6, 0.8, 1.0],
    },
}

def make_base_models():
    return {
        "LinearRegression": Pipeline([("scaler", StandardScaler()), ("m", LinearRegression())]),
        "Ridge": Pipeline([("scaler", StandardScaler()), ("m", Ridge(alpha=1.0, random_state=42))]),
        "RandomForest": RandomForestRegressor(n_estimators=200, max_depth=10, random_state=42, n_jobs=-1),
        "XGBoost": XGBRegressor(n_estimators=200, max_depth=5, learning_rate=0.08, random_state=42,
                                 n_jobs=-1, verbosity=0),
    }

def tuned_search(name, X_train, y_train, n_iter=8, cv=3):
    if name == "Ridge":
        est = Pipeline([("scaler", StandardScaler()), ("m", Ridge(random_state=42))])
        dist = {f"m__{k}": v for k, v in PARAM_DISTS["Ridge"].items()}
    elif name == "RandomForest":
        est = RandomForestRegressor(random_state=42, n_jobs=-1)
        dist = PARAM_DISTS["RandomForest"]
    elif name == "XGBoost":
        est = XGBRegressor(random_state=42, n_jobs=-1, verbosity=0)
        dist = PARAM_DISTS["XGBoost"]
    else:
        return None
    rs = RandomizedSearchCV(est, dist, n_iter=n_iter, cv=cv, scoring="r2",
                             random_state=42, n_jobs=-1)
    rs.fit(X_train, y_train)
    return rs

def run_market(market, prepared_df, results_path, sample_cap=3000, n_iter=8, cv=3):
    t0 = time.time()
    X, y, price = build_features(prepared_df, market, sample_cap=sample_cap)
    X_train, X_test, y_train, y_test, price_train, price_test = train_test_split(
        X, y, price, test_size=0.2, random_state=42)

    out = {"market": market, "n_train": len(X_train), "n_test": len(X_test),
           "n_features": X.shape[1], "feature_names": list(X.columns), "models": {}}

    base = make_base_models()
    for name, model in base.items():
        model.fit(X_train, y_train)
        out["models"][name] = {"before_tuning": evaluate(model, X_test, y_test, price_test)}
    print(f"  [{market}] baseline models done t={time.time()-t0:.1f}s", flush=True)

    for name in ["Ridge", "RandomForest", "XGBoost"]:
        rs = tuned_search(name, X_train, y_train, n_iter=n_iter, cv=cv)
        best = rs.best_estimator_
        out["models"][name]["after_tuning"] = evaluate(best, X_test, y_test, price_test)
        out["models"][name]["best_params"] = {k.replace("m__", ""): v for k, v in rs.best_params_.items()}
        out["models"][name]["cv_best_r2"] = round(float(rs.best_score_), 4)
        if name in ("RandomForest", "XGBoost"):
            imp = getattr(best, "feature_importances_", None)
            if imp is not None:
                order = np.argsort(imp)[::-1][:10]
                out["models"][name]["top_features_after_tuning"] = [
                    (X.columns[i], round(float(imp[i]), 4)) for i in order]
        print(f"  [{market}] {name} tuned t={time.time()-t0:.1f}s cv_r2={out['models'][name]['cv_best_r2']}", flush=True)

    out["elapsed_seconds"] = round(time.time() - t0, 1)

    if os.path.exists(results_path):
        with open(results_path) as f:
            all_results = json.load(f)
    else:
        all_results = {}
    all_results[market] = out
    with open(results_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    return out
