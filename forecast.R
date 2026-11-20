# Example forecast for the template challenge ("templatecast"): daily surface
# water temperature at three lakes, up to 30 days ahead.
#
# The model is deliberately simple: at each lake, tomorrow and every later day
# is a normal distribution with the mean and standard deviation of the lake's
# 14 most recent observations. Replace the "Forecast" section with your own
# model; keep the rest, which reads the targets and writes the file in the
# format the challenge expects.
#
# Run from the repository root:  Rscript forecast.R
#
# Environment variables (all optional)
#   REFERENCE_DATE  the day the forecast starts from, YYYY-MM-DD (default: today)
#   TARGETS_URL     where to read the challenge's targets (default: the published file)
#   S3_KEY, S3_SECRET  a key that can read the challenge's bucket. Set both when the
#                   bucket is private (ask the challenge for a read-only key); the
#                   targets are then downloaded with the key instead of by URL.

library(readr)
library(dplyr)

project_id <- "templatecast"          # the challenge's project_id
theme <- "lakes"                      # prefix of the file name, from the challenge
model_id <- "example_lake_model"      # must match challenge-model.yaml
horizon <- 30                         # days ahead

reference_date <- as.Date(Sys.getenv("REFERENCE_DATE", format(Sys.Date())))
targets_url <- Sys.getenv("TARGETS_URL", paste0(
  "https://s3.us-east-005.backblazeb2.com/template-challenge/targets/",
  "project_id=", project_id, "/duration=P1D/lakes-targets.csv.gz"
))

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
  minioclient::install_mc()
  minioclient::mc_alias_set("challenge", parts[2], key, secret)
  local <- tempfile(fileext = ".csv.gz")
  on.exit(unlink(local))
  minioclient::mc_cp(paste0("challenge/", parts[3]), shQuote(local))
  read_csv(local, show_col_types = FALSE, progress = FALSE)
}

# Targets: the observations so far ---------------------------------------------
targets <- read_targets(targets_url) |>
  filter(variable == "temperature", !is.na(observation), as.Date(datetime) <= reference_date)

# Forecast ----------------------------------------------------------------------
recent <- targets |>
  slice_max(datetime, n = 14, by = site_id) |>
  summarise(mu = mean(observation), sigma = max(sd(observation), 0.1), .by = site_id)

forecast <- recent |>
  cross_join(tibble(horizon = 1:horizon)) |>
  mutate(datetime = reference_date + horizon) |>
  tidyr::pivot_longer(c(mu, sigma), names_to = "parameter", values_to = "prediction")

# Standard format ---------------------------------------------------------------
# One row per site, date and distribution parameter. See the challenge's
# "How to forecast" page for the full description of the columns.
forecast <- forecast |>
  transmute(
    project_id = project_id,
    model_id = model_id,
    reference_datetime = reference_date,
    datetime,
    duration = "P1D",
    site_id,
    variable = "temperature",
    family = "normal",
    parameter,
    prediction
  )

# Write the file ----------------------------------------------------------------
# <theme>-<reference date>-<model_id>.csv.gz, in the folder challenge-model.yaml names.
dir.create("forecasts", showWarnings = FALSE)
file <- file.path("forecasts", paste0(theme, "-", reference_date, "-", model_id, ".csv.gz"))
write_csv(forecast, file)
message("Wrote ", file, " (", nrow(forecast), " rows)")
