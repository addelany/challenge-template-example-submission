# Example forecast for the template challenge ("templatecast"): daily surface water
# temperature at three lakes, up to 30 days ahead, as a 31-member ensemble.
#
# The model is a regression of water temperature on air temperature, driven by the NOAA
# GEFS weather ensemble from dynamical.org:
#
#   1. Weather. gefs_air_temperature.py reads daily mean 2 m air temperature at each lake
#      from the "NOAA GEFS forecast, 35 day" dataset on dynamical.org (https://dynamical.org),
#      which anyone can read over HTTPS with no account: for the past year (the weather
#      the lakes had) and for the 31 ensemble members of today's forecast run (the weather
#      to come).
#   2. Fit. At each lake, a linear regression of the observed water temperature on that
#      air temperature (lm(water ~ air)) over the past year.
#   3. Forecast. Each GEFS member's air temperature goes through the regression, plus a random
#      draw from the regression's residuals, to make one member of the water temperature
#      forecast. The 31 members are submitted as an ensemble: the weather uncertainty comes
#      from GEFS and the model's own uncertainty from the residuals.
#
# Replace the "Forecast" section with your own model; keep the rest, which reads the
# targets and the weather and writes the file in the format the challenge expects.
#
# Run from the repository root:  Rscript forecast.R
# Needs the R packages readr, dplyr and tidyr, and Python with the packages in
# requirements.txt (pip install -r requirements.txt) for the weather.
#
# Environment variables (all optional)
#   REFERENCE_DATE  the day the forecast starts from, YYYY-MM-DD (default: today). The newest
#                   GEFS run may not be complete yet; the latest complete one is used, and
#                   the file is named for its date.
#   TARGETS_URL     where to read the challenge's targets (default: the published file)
#   SITES_URL       the challenge's site list, with each lake's latitude and longitude
#   PYTHON          the Python to run (default: python3)
#   TRAIN_DAYS      days of history for the regression (default: 365)
#   S3_KEY, S3_SECRET  a key that can read the challenge's bucket. Set both when the
#                   bucket is private (ask the challenge for a read-only key); the
#                   targets are then downloaded with the key instead of by URL.
#                   This needs the minioclient and openssl packages.

library(readr)
library(dplyr)

project_id <- "templatecast"          # the challenge's project_id
theme <- "lakes"                      # prefix of the file name, from the challenge
model_id <- "example_lake_model"      # must match challenge-model.yaml
horizon <- 30                         # days ahead

requested_date <- as.Date(Sys.getenv("REFERENCE_DATE", format(Sys.Date())))
train_days <- as.integer(Sys.getenv("TRAIN_DAYS", "365"))
python <- Sys.getenv("PYTHON", "python3")
targets_url <- Sys.getenv("TARGETS_URL", paste0(
  "https://s3.us-east-005.backblazeb2.com/template-challenge/targets/",
  "project_id=", project_id, "/duration=P1D/lakes-targets.csv.gz"
))
sites_url <- Sys.getenv("SITES_URL",
  "https://raw.githubusercontent.com/rqthomas/challenge-template/main/sites.csv")

# Installing mc -----------------------------------------------------------------
# Reading with a key uses the MinIO client (mc). minioclient::install_mc() downloads
# it from dl.min.io, which MinIO has withdrawn (HTTP 410 Gone), so when that fails
# the pinned release is taken from GitHub instead and checked against its published
# SHA-256. In GitHub Actions the workflow has installed mc already.
ensure_mc <- function() {
  ok <- tryCatch({
    suppressWarnings(minioclient::install_mc())
    TRUE
  }, error = function(e) FALSE)
  if (ok) return(invisible())

  release <- "RELEASE.2025-08-13T08-35-41Z"
  os <- c(Linux = "linux", Darwin = "darwin", Windows = "windows")[[Sys.info()[["sysname"]]]]
  cpu <- if (Sys.info()[["machine"]] %in% c("arm64", "aarch64")) "arm64" else "amd64"
  asset <- paste0("mc.", os, "-", cpu, ".", release, if (os == "windows") ".exe")
  url <- paste0("https://github.com/minio/mc/releases/download/", release, "/", asset)
  dir <- getOption("minioclient.dir", tools::R_user_dir("minioclient", "data"))
  dir.create(dir, recursive = TRUE, showWarnings = FALSE)
  dest <- file.path(dir, if (os == "windows") "mc.exe" else "mc")

  options(timeout = max(600, getOption("timeout")))
  utils::download.file(url, dest, mode = "wb", quiet = TRUE)
  sums <- tempfile()
  utils::download.file(paste0(url, ".sha256sum"), sums, quiet = TRUE)
  expected <- strsplit(readLines(sums, n = 1), " ")[[1]][1]
  actual <- as.character(openssl::sha256(file(dest)))
  if (!isTRUE(actual == expected)) {
    unlink(dest)
    stop("The downloaded mc does not match its published checksum.")
  }
  Sys.chmod(dest, "755")
  invisible()
}

# Reading the targets -----------------------------------------------------------
# A public bucket is read by its URL. With S3_KEY and S3_SECRET set, the same
# address is read through the S3 API with the key, which also works when the bucket
# is private: the file is downloaded to a temporary folder first.
read_targets <- function(url) {
  key <- Sys.getenv("S3_KEY")
  secret <- Sys.getenv("S3_SECRET")
  if (!grepl("^https://", url) || !nzchar(key) || !nzchar(secret)) {
    return(read_csv(url, show_col_types = FALSE, progress = FALSE))
  }
  # https://<endpoint>/<bucket>/<object>
  parts <- regmatches(url, regexec("^https://([^/]+)/(.+)$", url))[[1]]
  ensure_mc()
  minioclient::mc_alias_set("challenge", parts[2], key, secret)
  local <- tempfile(fileext = ".csv.gz")
  on.exit(unlink(local))
  minioclient::mc_cp(paste0("challenge/", parts[3]), shQuote(local))
  read_csv(local, show_col_types = FALSE, progress = FALSE)
}

# Targets: the observed water temperature -----------------------------------------
targets <- read_targets(targets_url) |>
  filter(variable == "temperature", !is.na(observation),
         as.Date(datetime) <= requested_date) |>
  mutate(date = as.Date(datetime)) |>
  select(site_id, date, water_temperature = observation)
last_observed <- max(targets$date)
message("Targets: ", nrow(targets), " observations at ", n_distinct(targets$site_id),
        " lakes, the latest on ", last_observed)

# Weather: NOAA GEFS air temperature from dynamical.org --------------------------
# The lakes' coordinates come from the challenge's site list.
sites_file <- tempfile(fileext = ".csv")
download.file(sites_url, sites_file, quiet = TRUE)

# Runs gefs_air_temperature.py and reads back the CSV it writes.
gefs <- function(mode, ...) {
  out <- tempfile(fileext = ".csv")
  status <- system2(python, c("gefs_air_temperature.py", mode, sites_file, out, ...))
  if (status != 0 || !file.exists(out)) {
    stop("gefs_air_temperature.py failed. Is Python set up? Try: pip install -r requirements.txt",
         call. = FALSE)
  }
  read_csv(out, show_col_types = FALSE, progress = FALSE)
}

# The weather each lake had over the past year (the regression's input) ...
air_history <- gefs("history", "--date", format(last_observed), "--days", train_days)
# ... and the weather GEFS forecasts: one air temperature per ensemble member and day.
air_forecast <- gefs("forecast", "--date", format(requested_date), "--horizon", horizon)
reference_date <- as.Date(air_forecast$init_date[1])   # the GEFS run the forecast starts from
message("Forecast from the GEFS run of ", reference_date, ": ",
        n_distinct(air_forecast$ensemble_member), " members, ",
        n_distinct(air_forecast$date), " days")

# Forecast ----------------------------------------------------------------------
# One regression per lake: water temperature on air temperature.
training <- inner_join(targets, air_history |> mutate(date = as.Date(date)),
                       by = c("site_id", "date"))
models <- training |>
  group_by(site_id) |>
  group_map(function(d, key) {
    fit <- lm(water_temperature ~ air_temperature, data = d)
    message(key$site_id, ": water = ", round(coef(fit)[[1]], 2), " + ",
            round(coef(fit)[[2]], 2), " x air  (R2 ", round(summary(fit)$r.squared, 2),
            ", residual sd ", round(sigma(fit), 2), ", ", nrow(d), " days)")
    list(site_id = key$site_id, fit = fit, sigma = sigma(fit))
  }) |>
  (\(x) setNames(x, vapply(x, `[[`, "", "site_id")))()

set.seed(as.integer(reference_date))   # the same forecast every time it is made for a day
forecast <- air_forecast |>
  group_by(site_id) |>
  group_modify(function(d, key) {
    m <- models[[key$site_id]]
    # Member i's weather through the regression, plus a draw from the residuals.
    d$prediction <- predict(m$fit, newdata = d) + rnorm(nrow(d), 0, m$sigma)
    d
  }) |>
  ungroup()

# Standard format ---------------------------------------------------------------
# One row per site, date and ensemble member (the member number is the `parameter`).
# See the challenge's "How to forecast" page for the full description of the columns.
forecast <- forecast |>
  transmute(
    project_id = project_id,
    model_id = model_id,
    reference_datetime = reference_date,
    datetime = as.Date(date),
    duration = "P1D",
    site_id,
    variable = "temperature",
    family = "ensemble",
    parameter = ensemble_member,
    prediction
  )

# Write the file ----------------------------------------------------------------
# <theme>-<reference date>-<model_id>.csv.gz, in the folder challenge-model.yaml names.
dir.create("forecasts", showWarnings = FALSE)
file <- file.path("forecasts", paste0(theme, "-", reference_date, "-", model_id, ".csv.gz"))
write_csv(forecast, file)
message("Wrote ", file, " (", nrow(forecast), " rows)")
