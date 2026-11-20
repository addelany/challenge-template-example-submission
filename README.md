# Example submission to the template challenge

A complete, working example of submitting forecasts to a challenge **from a
GitHub repository**, built on the
challenge template (`eco4cast/challenge-template`;
project `templatecast`: daily surface water temperature at three lakes, up to
30 days ahead). Copy it as the starting point for your own model.

There is nothing to upload and no key to ask for. The challenge reads new files
from this repository, which only has to be **public**.

```
challenge-model.yaml   which model this repository submits, and its metadata
forecasts/             the forecast files: <theme>-<reference date>-<model_id>.csv.gz
forecast.R             makes a forecast and writes the file
.github/workflows/     optional: runs forecast.R every day and commits the file
```

## The model

`forecast.R` is deliberately simple: at each lake, every day of the horizon is a
normal distribution with the mean and standard deviation of the lake's 14 most
recent observations. Replace the "Forecast" section with your own model and keep
the rest.

```sh
Rscript forecast.R        # needs the readr, dplyr and tidyr packages
```

It writes `forecasts/lakes-<today>-example_lake_model.csv.gz`. The file in this
repository was made for 2026-11-19.

## What the challenge needs from you

1. **Forecast files** in the folder named in `challenge-model.yaml`
   (`forecasts/`). The name is `<theme>-<YYYY-MM-DD>-<model_id>.csv` or `.csv.gz`:
   `lakes` is this challenge's theme, the date is the day the forecast starts
   from, and the model id must match `challenge-model.yaml`. Columns:
   `project_id`, `model_id`, `reference_datetime`, `datetime`, `duration`,
   `site_id`, `variable`, `family`, `parameter` and `prediction`. A `normal`
   forecast has a `mu` and a `sigma` row for every site and date; an ensemble
   uses `family = sample` with the member number as `parameter`.
2. **`challenge-model.yaml`** at the top of the repository. It names the
   challenge (`templatecast`) and each model, and answers the questions of the
   model registration form; the challenge builds the model's catalog entry from
   it, and re-reads it when it changes. Leave out any question you do not want to
   answer.
3. **Registration.** Open the **Register a forecast repository** issue form on the
   challenge repository and give this repository's address. A bot checks it,
   adds it to the list of repositories the challenge reads, and closes the issue.

After that, every new file is checked the next time the challenge processes
submissions. What happened to each file, with the reason for any rejection, is
published at
`<forecasts bucket>/submission_results/example_lake_model.csv` (the challenge's
"How to forecast" page gives the address).

## Things to know

- A file is read **the first time it is seen**; editing it later has no effect.
  Add a new file for a new reference date instead.
- Only the repository registered for a `model_id` can submit as it, and a model id
  belongs to the first repository that registered it.
- A model id containing `example` is a test model: it is processed like any
  other but kept out of the challenge's catalog and analyses. This
  example uses one so that it can be tried safely. Pick your own id to be
  included.
- `challenge-model.yaml`'s `code_url` still says `YOUR-ACCOUNT`; set it to this
  repository's address when you publish it.

## If the challenge's bucket is private

By default `forecast.R` reads the targets by their public URL. If the challenge keeps
its bucket private, ask its organizers for a **read-only key**, then set two
environment variables and nothing else changes:

```sh
export S3_KEY=<key id> S3_SECRET=<application key>
Rscript forecast.R        # also needs the minioclient package
```

The script then reads the same address through the S3 API with the key: it downloads
the targets file to a temporary folder and reads that. In GitHub Actions add the
two values as repository secrets named `S3_KEY` and `S3_SECRET`; the workflow
passes them on. Never commit a key.

## Making a forecast every day

`.github/workflows/forecast.yml` runs `forecast.R` and commits the new file. Its
schedule is commented out: switch it on once the repository is registered and
the challenge's targets are published, since the forecast needs them. (Without
the schedule you can run it from the Actions tab.) Anything else that puts a
new file in `forecasts/` works as well: a cron job, a pipeline, a commit by hand.
