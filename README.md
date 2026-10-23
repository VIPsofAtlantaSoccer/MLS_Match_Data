# MLS Match Data

A Python application for downloading and processing Major League Soccer (MLS) and MLS NEXT Pro match data.

The project retrieves information from MLS APIs, stores the original JSON responses, and generates structured files for match analysis, roster management, and GameDay reporting.

The application supports multiple teams through TOML configuration.

## Features

- Download match data using an MLS match URL, slug, or match ID.
- Retrieve match metadata, statistics, rosters, key events, and commentary.
- Combine paginated commentary into a single JSON file.
- Generate roster CSV files and GameDay JSON reports.
- Retrieve season schedules, including upcoming fixtures.
- Identify existing match downloads to avoid unnecessary repeat downloads.
- Organize output by team, season, and match.
- Configure teams and output paths without modifying Python source code.

## Project Structure

```text
MLS_Match_Data/
├── MLS_Match_Data.py
├── MLS_API.py
├── MLS_Processing.py
├── MLS_Schedule.py
├── config.example.toml
├── config.toml
├── requirements.txt
├── .gitignore
└── README.md
```

### Python Modules

| File | Purpose |
|---|---|
| `MLS_Match_Data.py` | Main application for downloading and processing an individual match |
| `MLS_API.py` | Handles MLS API communication, match resolution, and endpoint downloads |
| `MLS_Processing.py` | Processes match data and generates roster and GameDay outputs |
| `MLS_Schedule.py` | Retrieves season fixtures and processes matches requiring downloads |

## Requirements

- Python 3.11 or newer
- Internet connectivity to access MLS APIs
- Python packages: `requests`, `rich`

Install the required packages:

```bash
pip install -r requirements.txt
```

## Configuration

Copy `config.example.toml` to `config.toml` and update the output directory and team settings.

Example:

```toml
[Application]
Output_Directory = "/Users/ericcross/Data/VIPs/Match_Stats"

[Rosters]
My_Team_Names = [
    "atlanta united",
    "atlanta united fc",
    "atl utd",
    "atlutd",
    "atlanta united 2",
    "atlutd2",
]

[Teams.ATLUTD]
Name = "Atlanta United"
Club_Id = "MLS-CLU-00000A"
Competition_Id = "MLS-COM-000001"

[Teams.ATLUTD2]
Name = "Atlanta United 2"
Club_Id = "MLS-CLU-00001W"
Competition_Id = "MLS-COM-000003"
```

`config.toml` contains local configuration and is excluded from Git. `config.example.toml` provides a tracked example.

Team IDs and competition IDs are used to retrieve the appropriate data from MLS APIs.

## Usage

### Download a single match

Run:

```bash
python MLS_Match_Data.py "atlvsclb-04-04-2026"
```

The application accepts three input formats.

**Match slug:**

```bash
python MLS_Match_Data.py "atlvsclb-04-04-2026"
```

**Match ID:**

```bash
python MLS_Match_Data.py "MLS-MAT-0009D6"
```

**Full match URL:**

```bash
python MLS_Match_Data.py "https://www.mlssoccer.com/competitions/mls-regular-season/2026/matches/atlvsclb-04-04-2026"
```

To override the configured output root:

```bash
python MLS_Match_Data.py "atlvsclb-04-04-2026" -output "/path/to/output"
```

### Retrieve a season schedule

Retrieve Atlanta United's 2026 schedule:

```bash
python MLS_Schedule.py ATLUTD 2026
```

Retrieve Atlanta United 2's 2026 schedule:

```bash
python MLS_Schedule.py ATLUTD2 2026
```

The schedule application retrieves fixtures through MLS APIs rather than scraping the schedule pages on MLSsoccer.com, ATLUTD.com, or MLSNEXTPro.com.

The season schedule includes future fixtures, even when final match statistics have not yet been published.

The application stores fixture information in a CSV and invokes the match downloader for matches requiring data. Existing completed downloads are skipped.

Currently, each team is associated with a configured competition ID. Matches in other competitions may require additional competition support.

## Output Structure

Downloaded matches are organized by team and year.

```text
Match_Stats/
├── ATLUTD/
│   └── 2026/
│       ├── MLS_Game_Links_ATLUTD_2026.csv
│       └── 2026-04-04-Atlanta United vs Columbus Crew/
│           ├── Resolved_Dapi.json
│           ├── Resolved_SportApi.json
│           ├── StatsApi_Match.json
│           ├── Match_Metadata.json
│           ├── Key_Events.json
│           ├── Club_Statistics.json
│           ├── Player_Statistics.json
│           ├── Commentary.json
│           ├── Rosters.csv
│           ├── GameDay_Lineup.json
│           ├── GameDay_Key_Events.json
│           ├── GameDay_Availability_Report.json
│           └── Manifest.json
└── ATLUTD2/
    └── 2026/
        └── ...
```

Additional JSON files are generated depending on the competition, available metadata, and API responses.

### Generated Files

| File | Description |
|---|---|
| `Rosters.csv` | Match-related roster data using `a` for the configured team and `o` for the opponent |
| `GameDay_Lineup.json` | Structured lineup information |
| `GameDay_Key_Events.json` | Structured match events |
| `GameDay_Availability_Report.json` | Player availability information and match metadata |
| `Match_Metadata.json` | Normalized information about the match, teams, officials, venue, and environment |
| `Commentary.json` | Combined commentary retrieved across API pages |
| `Manifest.json` | Resolved metadata, requested endpoints, and download results |
| `MLS_Game_Links_<TEAM>_<YEAR>.csv` | Season fixtures, match identifiers, dates, teams, and available URLs |

## API Sources

The application retrieves data from several MLS services:

- **DAPI:** Match content and identifiers.
- **SportAPI:** Match identity, clubs, and venue information.
- **StatsAPI:** Match metadata, statistics, rosters, events, commentary, and season schedules.
- **MLS Vocabulary API:** Supplemental reference information.

MLS API endpoints are external services and may change without notice.

Some information may not be available before kickoff or immediately after a match concludes. The absence of unpublished statistics does not necessarily indicate an invalid match identifier.

## Download Behavior

The single-match application retrieves available API data and generates its associated output files.

The schedule application is designed for repeat execution:

1. Retrieve the configured team's season fixtures.
2. Save the schedule CSV, including future matches.
3. Identify matches already downloaded successfully.
4. Download missing or incomplete match data.
5. Leave matches with unpublished information eligible for later updates.

This supports retrieving a season incrementally as matches are scheduled and played.

## Development

The project separates responsibilities among the main application, API communication, and data processing.

Python source follows the project's naming conventions, including Pascal_Snake_Case for application variables and functions.

The project originated from several standalone MLS data-retrieval and processing scripts that were consolidated into reusable modules.

## Disclaimer

This is an independent project and is not affiliated with, endorsed by, or maintained by Major League Soccer, MLS NEXT Pro, or their clubs.

All match data remains subject to the availability and terms of the respective data providers.