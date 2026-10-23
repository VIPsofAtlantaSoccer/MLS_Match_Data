
#---------------------------------------------------------------------------------------------------------------#
# MLS Schedule
#
# Retrieve a team's season fixtures and download matches that are not yet complete.
#---------------------------------------------------------------------------------------------------------------#
import argparse
import csv
import json
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any, Dict, List

from MLS_API import Create_Session, Get_Json


#---------------------------------------------------------------------------------------------------------------#
# Load existing configuration from config.toml
# Returns the configuration dictionary
#---------------------------------------------------------------------------------------------------------------#
def Load_Config() -> Dict[str, Any]:
    Config_File = Path( __file__ ).resolve().parent / "config.toml"

    with Config_File.open( "rb" ) as File_Handle:
        return tomllib.load( File_Handle )


#---------------------------------------------------------------------------------------------------------------#
# Resolve a competition's season ID from the official MLS API
# Returns the season ID matching the requested year
#---------------------------------------------------------------------------------------------------------------#
def Resolve_Season_Id( Session: Any, Competition_Id: str, Season: int ) -> str:
    Url = f"https://stats-api.mlssoccer.com/competitions/{Competition_Id}/seasons"
    Success, Data, Status_Code, _ = Get_Json( Session, Url )

    if ( not Success ) or ( not isinstance( Data, dict ) ):
        raise RuntimeError( f"Season lookup failed for {Competition_Id}: HTTP {Status_Code}" )

    for Season_Data in Data.get( "seasons", [] ):
        if ( str( Season_Data.get( "season" ) ) == str( Season ) ):
            return Season_Data[ "season_id" ]

    raise RuntimeError( f"No season ID returned for {Competition_Id}, {Season}" )


#---------------------------------------------------------------------------------------------------------------#
# Retrieve the season's matches and select the configured club by its Sportec ID
# Returns a list of schedule records including future fixtures
#---------------------------------------------------------------------------------------------------------------#
def Fetch_Season_Matches( Session: Any, Club_Id: str, Competition_Id: str, Season_Id: str, Season: int ) -> List[Dict[str, Any]]:
    Url = (
        f"https://stats-api.mlssoccer.com/matches/seasons/{Season_Id}"
        f"?match_date%5Bgte%5D={Season}-01-01"
        f"&match_date%5Blte%5D={Season}-12-31"
        f"&per_page=1000"
    )

    Success, Data, Status_Code, _ = Get_Json( Session, Url )

    if ( not Success ) or ( not isinstance( Data, dict ) ):
        raise RuntimeError( f"Schedule lookup failed: HTTP {Status_Code}" )

    Matches = Data.get( "schedule" )

    if ( not isinstance( Matches, list ) ):
        raise RuntimeError( "Schedule response did not contain a schedule list." )

    if ( len( Matches ) >= 1000 ):
        raise RuntimeError( "Schedule reached 1000 records; refusing an incomplete list." )

    Selected = []

    for Match in Matches:
        if ( not isinstance( Match, dict ) ):
            continue

        if ( Club_Id not in ( Match.get( "home_team_id" ), Match.get( "away_team_id" ) ) ):
            continue

        if ( not Match.get( "match_id" ) ):
            continue

        Selected.append( Match )

    return sorted( Selected, key = lambda Match: Match.get( "planned_kickoff_time" ) or "" )


#---------------------------------------------------------------------------------------------------------------#
# Look up a match's website URL and venue details when available
# Returns a dictionary of available schedule details
#---------------------------------------------------------------------------------------------------------------#
def Resolve_Match_Details( Session: Any, Match_Id: str, Season: int ) -> Dict[str, str]:
    Url = f"https://sportapi.mlssoccer.com/api/matches/{Match_Id}"
    Success, Data, _, _ = Get_Json( Session, Url )

    Details = {
        "URL": "",
        "Venue": "",
    }

    if ( not Success ) or ( not isinstance( Data, dict ) ):
        return Details

    Slug = Data.get( "slug" )
    Competition = Data.get( "competition" ) or {}
    Competition_Slug = Competition.get( "slug" ) if isinstance( Competition, dict ) else None

    if ( Slug ) and ( Competition_Slug ):
        Details[ "URL" ] = f"https://www.mlssoccer.com/competitions/{Competition_Slug}/{Season}/matches/{Slug}"

    Venue = Data.get( "venue" ) or {}

    if ( isinstance( Venue, dict ) ):
        Details[ "Venue" ] = Venue.get( "name" ) or ""

    return Details


#---------------------------------------------------------------------------------------------------------------#
# Write the complete fixture schedule to CSV, including future matches and available URLs
# Returns the CSV file path
#---------------------------------------------------------------------------------------------------------------#
def Write_Schedule_CSV( Matches: List[Dict[str, Any]], Session: Any, Output_File: Path, Season: int ) -> Path:
    Columns = [
        "Match_Id", "Date", "Kickoff", "Competition", "Home_Team", "Away_Team",
        "Venue", "City", "Match_Day", "URL",
    ]

    Output_File.parent.mkdir( parents = True, exist_ok = True )

    with Output_File.open( "w", newline = "", encoding = "utf-8" ) as File_Handle:
        Writer = csv.DictWriter( File_Handle, fieldnames = Columns )
        Writer.writeheader()

        for Match in Matches:
            Kickoff = Match.get( "planned_kickoff_time" ) or ""
            Details = Resolve_Match_Details( Session, Match[ "match_id" ], Season )

            Writer.writerow( {
                "Match_Id": Match[ "match_id" ],
                "Date": Kickoff[:10],
                "Kickoff": Kickoff,
                "Competition": Match.get( "competition_name" ) or "",
                "Home_Team": Match.get( "home_team_name" ) or "",
                "Away_Team": Match.get( "away_team_name" ) or "",
                "Venue": Match.get( "stadium_name" ) or Details[ "Venue" ],
                "City": Match.get( "stadium_city" ) or "",
                "Match_Day": Match.get( "match_day" ) or "",
                "URL": Details[ "URL" ],
            } )

    return Output_File


#---------------------------------------------------------------------------------------------------------------#
# Determine whether an existing match has full downloaded outputs after its scheduled kickoff
# Returns True only when the download is complete and the fixture is no longer provisional
#---------------------------------------------------------------------------------------------------------------#
def Is_Match_Complete( Match: Dict[str, Any], Output_Directory: Path ) -> bool:
    Match_Id = Match[ "match_id" ]
    Kickoff_Text = Match.get( "planned_kickoff_time" )

    if ( not Kickoff_Text ):
        return False

    try:
        Kickoff = datetime.fromisoformat( Kickoff_Text.replace( "Z", "+00:00" ) )

        if ( Kickoff.tzinfo is None ):
            Kickoff = Kickoff.replace( tzinfo = timezone.utc )

    except ValueError:
        return False

    if ( datetime.now( timezone.utc ) < Kickoff + timedelta( hours = 3 ) ):
        return False

    Required_Files = (
        "Rosters.csv",
        "GameDay_Lineup.json",
        "GameDay_Key_Events.json",
        "GameDay_Availability_Report.json",
    )

    for Manifest_File in Output_Directory.glob( "*/Manifest.json" ):
        try:
            with Manifest_File.open( "r", encoding = "utf-8" ) as File_Handle:
                Manifest = json.load( File_Handle )

            if ( Manifest.get( "Resolved_Metadata", {} ).get( "Match_Id" ) != Match_Id ):
                continue

            Summary = Manifest.get( "Download_Summary", {} )

            if ( Summary.get( "Failed" ) ) or ( Summary.get( "Skipped" ) ):
                return False

            if ( not all( ( Manifest_File.parent / Name ).is_file() for Name in Required_Files ) ):
                return False

            Modified = datetime.fromtimestamp( Manifest_File.stat().st_mtime, tz = timezone.utc )

            return Modified >= Kickoff + timedelta( hours = 3 )

        except ( OSError, ValueError, TypeError, AttributeError ):
            continue

    return False


#---------------------------------------------------------------------------------------------------------------#
# Download missing matches through MLS_Match_Data.py and retain future fixtures for later updates
# Returns counts of downloaded, skipped, and pending matches
#---------------------------------------------------------------------------------------------------------------#
def Download_Matches( Matches: List[Dict[str, Any]], Output_Directory: Path ) -> Dict[str, int]:
    Application_File = Path( __file__ ).resolve().parent / "MLS_Match_Data.py"

    Counts = {
        "Downloaded": 0,
        "Skipped": 0,
        "Pending": 0,
    }

    for Match in Matches:
        Match_Id = Match[ "match_id" ]

        if ( Is_Match_Complete( Match, Output_Directory ) ):
            Counts[ "Skipped" ] += 1
            print( f"SKIP: {Match_Id}" )
            continue

        print( f"DOWNLOAD: {Match_Id} - {Match.get( 'home_team_name' )} vs {Match.get( 'away_team_name' )}" )

        Result = subprocess.run(
            [ sys.executable, str( Application_File ), Match_Id ],
            check = False,
        )

        if ( Result.returncode == 0 ):
            Counts[ "Downloaded" ] += 1
        else:
            Counts[ "Pending" ] += 1
            print( f"PENDING: {Match_Id} (download exit code {Result.returncode})" )

    return Counts

#---------------------------------------------------------------------------------------------------------------#
# Determine whether a finished match already has all required downloaded outputs
# Returns True only when the match is final and its saved outputs are complete
#---------------------------------------------------------------------------------------------------------------#
def Is_Match_Complete( Match: Dict[str, Any], Output_Directory: Path ) -> bool:
    Match_Id = Match[ "match_id" ]
    Match_Status = Match.get( "match_status" )

    if ( Match_Status != "FullTime" ):
        return False

    Required_Files = (
        "Rosters.csv",
        "GameDay_Lineup.json",
        "GameDay_Key_Events.json",
        "GameDay_Availability_Report.json",
    )

    for Manifest_File in Output_Directory.glob( "*/Manifest.json" ):
        try:
            with Manifest_File.open( "r", encoding = "utf-8" ) as File_Handle:
                Manifest = json.load( File_Handle )

            if ( Manifest.get( "Resolved_Metadata", {} ).get( "Match_Id" ) != Match_Id ):
                continue

            Summary = Manifest.get( "Download_Summary", {} )

            if ( Summary.get( "Failed" ) ) or ( Summary.get( "Skipped" ) ):
                return False

            if ( not all( ( Manifest_File.parent / Name ).is_file() for Name in Required_Files ) ):
                return False

            return True

        except ( OSError, ValueError, TypeError, AttributeError ):
            continue

    return False

#---------------------------------------------------------------------------------------------------------------#
# Retrieve the configured club's fixtures, store the schedule, and download missing matches
# Returns the process exit code
#---------------------------------------------------------------------------------------------------------------#
def Main() -> int:
    Parser = argparse.ArgumentParser( description = "Retrieve MLS season schedule and missing match data" )
    Parser.add_argument( "Team", help = "Team key defined in config.toml, such as ATLUTD or ATLUTD2" )
    Parser.add_argument( "Season", type = int, help = "Season year, such as 2026" )

    Arguments = Parser.parse_args()

    try:
        Config = Load_Config()
        Team_Key = Arguments.Team.upper()
        Team_Config = Config[ "Teams" ][ Team_Key ]

        Club_Id = Team_Config[ "Club_Id" ]
        Competition_Id = Team_Config[ "Competition_Id" ]
        Output_Directory = Path( Config[ "Application" ][ "Output_Directory" ] ).expanduser()

        Session = Create_Session()
        Season_Id = Resolve_Season_Id( Session, Competition_Id, Arguments.Season )
        Matches = Fetch_Season_Matches( Session, Club_Id, Competition_Id, Season_Id, Arguments.Season )

        if ( not Matches ):
            raise RuntimeError( f"No matches returned for {Team_Key} in {Arguments.Season}; CSV not overwritten." )

        Team_Output_Directory = Output_Directory / Team_Key / str( Arguments.Season )
        Output_File = Team_Output_Directory / f"MLS_Game_Links_{Team_Key}_{Arguments.Season}.csv"

        Write_Schedule_CSV( Matches, Session, Output_File, Arguments.Season )

        print( f"Team: {Team_Key} | Season: {Arguments.Season} | Matches: {len( Matches )}" )
        print( f"Schedule: {Output_File}" )

        Counts = Download_Matches( Matches, Team_Output_Directory )

        print(
            f"Downloaded: {Counts[ 'Downloaded' ]} | "
            f"Skipped: {Counts[ 'Skipped' ]} | "
            f"Pending: {Counts[ 'Pending' ]}"
        )

        return 0

    except ( FileNotFoundError, KeyError, ValueError, RuntimeError, OSError ) as Error:
        print( f"ERROR: {Error}", file = sys.stderr )
        return 1


if ( __name__ == "__main__" ):
    raise SystemExit( Main() )
