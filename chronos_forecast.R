
# Requires the Python package 'chronos-forecasting' to be installed in the
# active reticulate environment:
#   reticulate::py_install("chronos-forecasting", pip = TRUE)
#
# Chronos-Bolt (Chronos2) model card: https://huggingface.co/amazon/chronos-bolt-small
# Available model sizes: chronos-bolt-tiny, -mini, -small, -base, -large

# source model function
source('./chronos_function.R')

print(paste0("Running Chronos at ", Sys.time()))

library(tidyverse)
library(lubridate)
library(aws.s3)
library(imputeTS)
library(tsibble)
library(fable)

# Sys.unsetenv("AWS_DEFAULT_REGION")
# Sys.unsetenv("AWS_S3_ENDPOINT")
# Sys.setenv("AWS_EC2_METADATA_DISABLED"="TRUE")

# --- Python setup via reticulate ---
Sys.setenv("TOKENIZERS_PARALLELISM" = "false")
Sys.setenv("TRANSFORMERS_NO_ADVISORY_WARNINGS" = "1")

team_name <- 'chronos2'

# --- Python setup via reticulate ---
print('set up torch')
torch   <- reticulate::import("torch")

print('set up chronos')
chronos <- reticulate::import("chronos")


# Read in targets
targets_insitu <- readr::read_csv(paste0("https://amnh1.osn.mghpcc.org/bio230121-bucket01/vera4cast/targets/project_id=vera4cast/duration=P1D/daily-insitu-targets.csv.gz"), guess_max = 10000)
# targets_met <- readr::read_csv(paste0("https://", config$endpoint, "/", config$targets_bucket, "/project_id=vera4cast/duration=P1D/daily-met-targets.csv.gz"), guess_max = 10000, show_col_types = FALSE)
# targets_tubr <- readr::read_csv(paste0("https://", config$endpoint, "/", config$targets_bucket, "/project_id=vera4cast/duration=P1D/daily-inflow-targets.csv.gz"), guess_max = 10000, show_col_types = FALSE)


# set run date
curr_reference_datetime <- Sys.Date()

# Insitu variables
# get all combinations
print('Insitu model')

site_var_combinations <- expand.grid(var = c('Temp_C_mean'),
                                     site = c('fcre',
                                              'bvre'))

chronos_insitu <- purrr::pmap_dfr(site_var_combinations,
                                  .f = ~ generate_chronos_forecast(targets = targets_insitu,
                                                                   h = 35,
                                                                   model_name = team_name,
                                                                   forecast_date = curr_reference_datetime,
                                                                   depth = 'target',
                                                                   ...))
file_date <- chronos_insitu$reference_datetime[1]
forecast_file <- paste0(paste("daily", file_date, team_name, sep = "-"), ".csv.gz")

write.csv(chronos_insitu, paste0('./forecasts/',forecast_file))
