# Аудит исходного архива 2026-06-30

## Состав

- FastAPI application with file upload UI.
- `audio`: loader/preprocessing/features/separation/analyzer.
- `classification`: expert profiles.
- `ml`: 43-feature dataset and standardized KNN/centroid model.
- `localization`: GCC-PHAT and least-squares local x/y/z TDOA.
- `tracking`: 0.5 s window tracker with no-op Kalman placeholder.
- 31 unit tests.

## Проверено

`PYTHONPATH=. pytest -q` on the unmodified extracted source: 31 PASS.

Dataset: 840 windows, 43 numerical feature columns, 8 labels. Model type: `standardized_knn_centroid`, k=9 in configuration.

## Проблемы исходной поставки

1. The tracker contains `KalmanFilterHook` that returns points unchanged.
2. Localization uses uploaded synchronized files and local x/y/z coordinates, not station GNSS/PPS streaming.
3. No persistent live station/event database or streaming ingress.
4. No network event correlation rule one station -> warning, 2+ -> alert.
5. No live target velocity vector / altitude fusion from distributed stations.
6. No device command/audio request channel.
7. Russian directory names inside ZIP were encoded as UTF-8 bytes but interpreted as CP437 during extraction. Working copy repaired.
8. FP-1 raw source referenced by `features.csv` is missing from the archive. The trained model remains usable, but full dataset retraining is not reproducible from the archive alone.
9. Current preprocessing normalizes the complete loaded recording before window extraction. Embedded streaming must reproduce the same preprocessing convention or the model must be rebuilt with the final station-window convention.

## Changes in ZS branch

See `README_ZS_BPLA.md` and `station/`, `fusion/`.
