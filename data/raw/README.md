# Raw datasets

The third-party datasets and the generated SUMO output are several GB and are
not part of the repository. Put them in one folder and set SCS_DATA_DIR to it;
evaluation.real_datasets.data_root() defaults to ./datasets. Preprocessing
turns each source into the project's Telemetry schema; a small sample of each
is in data/processed/.

| Subfolder of SCS_DATA_DIR | Dataset | Source | Licence |
|---|---|---|---|
| ngsim/ngsim_full.csv | NGSIM: real vehicle trajectories on the Lankershim and Peachtree signalised arterials (2,481,206 rows) | bash scripts/download_usdot_open_data.sh, which calls https://data.transportation.gov/resource/8ect-6jqj.csv (open API, no account) | public domain |
| pneuma/ | pNEUMA: drone-recorded vehicle trajectories over central Athens (15.8 GB, 220 files) | Zenodo record 10491409, https://zenodo.org/records/10491409; extract pNEUMA_dataset.zip into pneuma/extracted/ | CC BY 4.0 |
| veremi/ | VeReMi Extension: simulated V2X messages with labelled attacks | Zenodo record 20090854; keep the per-attack zip files | CC BY 4.0 |
| sumo/sumo_fcd_full.csv | SUMO floating-car data from a signalised four-arm intersection, 1,100 vehicles per hour over 40 minutes (39,629 rows) | python -m smart_city_security.integration.sumo_scenario | generated |

NGSIM files from the Socrata export endpoint
(/api/views/.../rows.csv?accessType=DOWNLOAD) use PascalCase column names such
as Vehicle_ID, unlike the resource endpoint used here (/resource/....csv, with
lowercase vehicle_id). The adapter evaluation.real_datasets.ngsim_rows_to_telemetry
expects the lowercase resource-endpoint columns.
