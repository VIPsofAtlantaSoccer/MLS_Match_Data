
#---------------------------------------------------------------------------------------------------------------#
# MLS Match Data
#
# Main application for downloading and processing MLS match data.
#---------------------------------------------------------------------------------------------------------------#
import argparse
import json
import sys
import tomllib
from pathlib import Path
from typing import Any, Dict
from rich import print

from MLS_API import *
from MLS_Processing import *


#---------------------------------------------------------------------------------------------------------------#
# Load application configuration from config.toml
# Returns the configuration dictionary
#---------------------------------------------------------------------------------------------------------------#
def Load_Config() -> Dict[str, Any]:
    Config_File = Path( __file__ ).resolve().parent / "config.toml"

    if ( not Config_File.is_file() ):
        raise FileNotFoundError(
            f"Configuration file not found: {Config_File}\n"
            "Copy config.example.toml to config.toml."
        )

    with Config_File.open( "rb" ) as File_Handle:
        Config = tomllib.load( File_Handle )

    return Config


#---------------------------------------------------------------------------------------------------------------#
# Parse the command-line arguments for a single MLS match download
# Returns the parsed arguments
#---------------------------------------------------------------------------------------------------------------#
def Parse_Arguments() -> argparse.Namespace:
    Parser = argparse.ArgumentParser( description = "Download MLS JSON data for a single match" )
    Parser.add_argument( "Input_Value", help = "MLS match URL, slug, or match id" )
    Parser.add_argument( "-output", default = None, help = "Base output directory" )
    return Parser.parse_args()


#---------------------------------------------------------------------------------------------------------------#
# Resolve the supplied match and retrieve available match metadata from MLS APIs
# Returns match identifiers and the three source API payloads
#---------------------------------------------------------------------------------------------------------------#
def Resolve_Match_Data( Session: Any, Input_Value: str ) -> Dict[str, Any]:
    Match_Id, Match_Slug, Dapi_Data, SportApi_Data = Resolve_Input( Session = Session, Input_Value = Input_Value )

    if ( Dapi_Data is None ):
        Dapi_Data = Resolve_Match_From_Slug( Session, Match_Slug )

    StatsApi_Data = None
    try:
        StatsApi_Data = Resolve_Match_From_StatsApi( Session = Session, Match_Id = Match_Id )
    except RuntimeError as Error:
        print( f"WARNING: {Error}", file = sys.stderr )

    if ( SportApi_Data is None ):
        try:
            SportApi_Data = Resolve_Match_From_Id( Session = Session, Match_Id = Match_Id )
        except RuntimeError as Error:
            print( f"WARNING: {Error}", file = sys.stderr )
            SportApi_Data = None

    if ( StatsApi_Data is None ) and ( SportApi_Data is None ):
        raise RuntimeError(
            f"Could not resolve match [{Match_Id}] from StatsAPI or SportAPI. "
            "The match id may be valid, but match data may not be published yet."
        )

    Resolved_Metadata = Build_Resolved_Metadata(
        Match_Id = Match_Id,
        Match_Slug = Match_Slug,
        Dapi_Data = Dapi_Data,
        SportApi_Data = SportApi_Data,
        StatsApi_Data = StatsApi_Data,
    )

    return {
        "Match_Id": Match_Id,
        "Match_Slug": Match_Slug,
        "Dapi_Data": Dapi_Data,
        "SportApi_Data": SportApi_Data,
        "StatsApi_Data": StatsApi_Data,
        "Resolved_Metadata": Resolved_Metadata,
    }


#---------------------------------------------------------------------------------------------------------------#
# Resolve the configured team's season output directory for a match
# Returns the full match output directory path
#---------------------------------------------------------------------------------------------------------------#
def Build_Output_Directory( Config: Dict[str, Any], Output_Directory: str, Match_Data: Dict[str, Any] ) -> Path:
    Resolved_Metadata = Match_Data[ "Resolved_Metadata" ]
    Home_Team_Id = Resolved_Metadata.get( "Home_Team_Id" )
    Away_Team_Id = Resolved_Metadata.get( "Away_Team_Id" )

    Matching_Teams = [
        Team_Key for Team_Key, Team_Data in Config[ "Teams" ].items()
        if ( Team_Data[ "Club_Id" ] in ( Home_Team_Id, Away_Team_Id ) )
    ]

    if ( len( Matching_Teams ) != 1 ):
        raise ValueError( f"Could not uniquely identify a configured team for match {Match_Data[ 'Match_Id' ]}" )

    Team_Key = Matching_Teams[ 0 ]
    Match_Year = Resolved_Metadata[ "Match_Date" ][ :4 ]
    Match_Folder_Name = Build_Match_Folder_Name( Resolved_Metadata )
    Match_Output_Directory = Path( Output_Directory ) / Team_Key / Match_Year / Match_Folder_Name
    Match_Output_Directory.mkdir( parents = True, exist_ok = True )
    return Match_Output_Directory


#---------------------------------------------------------------------------------------------------------------#
# Save resolved match payloads and download the available MLS API endpoints
# Returns the endpoint dictionary and download summary
#---------------------------------------------------------------------------------------------------------------#
def Download_Match_Endpoints( Session: Any, Match_Data: Dict[str, Any], Match_Output_Directory: Path ) -> Dict[str, Any]:
    Match_Id = Match_Data[ "Match_Id" ]
    Match_Slug = Match_Data[ "Match_Slug" ]
    Dapi_Data = Match_Data[ "Dapi_Data" ]
    SportApi_Data = Match_Data[ "SportApi_Data" ]
    StatsApi_Data = Match_Data[ "StatsApi_Data" ]
    Resolved_Metadata = Match_Data[ "Resolved_Metadata" ]

    Endpoints = Build_Endpoint_List(
        Match_Id = Match_Id,
        Match_Slug = Match_Slug,
        Season_Id = Resolved_Metadata.get( "Season_Id" ),
        Competition_Id = Resolved_Metadata.get( "Competition_Id" ),
        Home_Team_Id = Resolved_Metadata.get( "Home_Team_Id" ),
        Away_Team_Id = Resolved_Metadata.get( "Away_Team_Id" ),
        Home_Team = Resolved_Metadata.get( "Home_Team" ),
        Away_Team = Resolved_Metadata.get( "Away_Team" ),
        Match_Date = Resolved_Metadata.get( "Match_Date" ),
    )

    Save_Response( Match_Output_Directory / "Resolved_Dapi.json", Dapi_Data )

    if ( SportApi_Data is not None ):
        Save_Response( Match_Output_Directory / "Resolved_SportApi.json", SportApi_Data )

    if ( StatsApi_Data is not None ):
        Save_Response( Match_Output_Directory / "StatsApi_Match.json", StatsApi_Data )
        Match_Metadata = Build_Match_Metadata( Match_Id = Match_Id, Match_Slug = Match_Slug, StatsApi_Data = StatsApi_Data )
        Save_Response( Match_Output_Directory / "Match_Metadata.json", Match_Metadata )
    else:
        Download_Error = {
            "Match_Id": Match_Id,
            "Match_Slug": Match_Slug,
            "Error": "StatsAPI match data is not available.",
            "Message": "The match id may be valid, but StatsAPI has not published match data yet.",
        }
        #Save_Response( Match_Output_Directory / "Download_Error.json", Download_Error )

    Download_Summary = Download_All_Endpoints( Session = Session, Endpoints = Endpoints, Output_Directory = Match_Output_Directory )
    return { "Endpoints": Endpoints, "Download_Summary": Download_Summary }


#---------------------------------------------------------------------------------------------------------------#
# Refresh resolved match metadata using the downloaded season match window
# Returns the updated resolved metadata dictionary
#---------------------------------------------------------------------------------------------------------------#
def Refresh_Resolved_Metadata( Match_Data: Dict[str, Any], Match_Output_Directory: Path ) -> Dict[str, Any]:
    Resolved_Metadata = Match_Data[ "Resolved_Metadata" ]
    Season_Match_Window_File = Match_Output_Directory / "Season_Match_Window.json"

    if ( Season_Match_Window_File.exists() ):
        with Season_Match_Window_File.open( "r", encoding = "utf-8" ) as File_Handle:
            Season_Match_Window_Data = json.load( File_Handle )

        Resolved_Metadata = Build_Resolved_Metadata(
            Match_Id = Match_Data[ "Match_Id" ],
            Match_Slug = Match_Data[ "Match_Slug" ],
            Dapi_Data = Match_Data[ "Dapi_Data" ],
            SportApi_Data = Match_Data[ "SportApi_Data" ],
            StatsApi_Data = Match_Data[ "StatsApi_Data" ],
            Season_Match_Window_Data = Season_Match_Window_Data,
        )

    Match_Data[ "Resolved_Metadata" ] = Resolved_Metadata
    return Resolved_Metadata


#---------------------------------------------------------------------------------------------------------------#
# Download paginated commentary and update the endpoint summary
# Returns commentary counters and the downloaded payload
#---------------------------------------------------------------------------------------------------------------#
def Download_Match_Commentary( Session: Any, Match_Id: str, Match_Output_Directory: Path, Download_Summary: Dict[str, Any] ) -> Dict[str, Any]:
    Commentary_Success, Commentary_Data, Commentary_Page_Count, Commentary_Duplicate_Count, Commentary_Status_Code, Commentary_Error_Data = Download_All_Commentary(
        Session = Session,
        Match_Id = Match_Id,
    )

    Commentary_Url = f"https://stats-api.mlssoccer.com/matches/{Match_Id}/commentary?language=en"

    if ( Commentary_Success ):
        Save_Response( Match_Output_Directory / "Commentary.json", Commentary_Data )
        Download_Summary[ "Downloaded" ][ "Commentary" ] = {
            "Url": Commentary_Url,
            "Status_Code": Commentary_Status_Code,
            "Content_Type": "application/json",
            "Output_File": str( Match_Output_Directory / "Commentary.json" ),
            "Pages_Downloaded": Commentary_Page_Count,
            "Commentary_Items": len( Commentary_Data.get( "commentary", [] ) ),
            "Commentary_Duplicates_Skipped": Commentary_Duplicate_Count,
        }
    else:
        Commentary_Error_File = Match_Output_Directory / "Commentary.error.json"
        #Save_Response( Commentary_Error_File, Commentary_Error_Data )

        if ( "Skipped" not in Download_Summary ):
            Download_Summary[ "Skipped" ] = {}

        Download_Summary[ "Skipped" ][ "Commentary" ] = {
            "Url": Commentary_Url,
            "Status_Code": Commentary_Status_Code,
            "Output_File": str( Commentary_Error_File ),
            "Pages_Downloaded": Commentary_Page_Count,
            "Commentary_Duplicates_Skipped": Commentary_Duplicate_Count,
        }

    return {
        "Commentary_Data": Commentary_Data,
        "Commentary_Page_Count": Commentary_Page_Count,
        "Commentary_Duplicate_Count": Commentary_Duplicate_Count,
    }


#---------------------------------------------------------------------------------------------------------------#
# Save the match manifest and generate roster, availability, and lineup outputs
# Returns nothing
#---------------------------------------------------------------------------------------------------------------#
def Generate_Match_Outputs( Config: Dict[str, Any], Match_Data: Dict[str, Any], Match_Output_Directory: Path, Endpoint_Data: Dict[str, Any] ) -> None:
    Manifest = {
        "Resolved_Metadata": Match_Data[ "Resolved_Metadata" ],
        "Endpoints": Endpoint_Data[ "Endpoints" ],
        "Download_Summary": Endpoint_Data[ "Download_Summary" ],
    }
    Save_Response( Match_Output_Directory / "Manifest.json", Manifest )
    Generate_GameDay_Availability_Report( Match_Output_Directory, Match_Data[ "Resolved_Metadata" ] )
    Generate_Match_Lineup_JSON( Match_Output_Directory = Match_Output_Directory )


#---------------------------------------------------------------------------------------------------------------#
# Identify the configured team and opponent from resolved metadata
# Returns a tuple containing the configured team and its opponent
#---------------------------------------------------------------------------------------------------------------#
def Resolve_Team_Names( Config: Dict[str, Any], Resolved_Metadata: Dict[str, Any] ) -> tuple[str, str]:
    Home_Team = Resolved_Metadata.get( "Home_Team", "" )
    Away_Team = Resolved_Metadata.get( "Away_Team", "" )
    My_Team_Names = { Name.lower() for Name in Config[ "Rosters" ][ "My_Team_Names" ] }

    if ( Home_Team.lower() in My_Team_Names ):
        return Home_Team, Away_Team
    elif ( Away_Team.lower() in My_Team_Names ):
        return Away_Team, Home_Team

    raise ValueError( f"Neither team matches My_Team_Names: {Home_Team} vs {Away_Team}" )


#---------------------------------------------------------------------------------------------------------------#
# Print the match details, commentary counts, and failed download information
# Returns the process exit code
#---------------------------------------------------------------------------------------------------------------#
def Print_Match_Summary( Config: Dict[str, Any], Match_Data: Dict[str, Any], Match_Output_Directory: Path, Endpoint_Data: Dict[str, Any], Commentary_Result: Dict[str, Any] ) -> int:
    Resolved_Metadata = Match_Data[ "Resolved_Metadata" ]
    Download_Summary = Endpoint_Data[ "Download_Summary" ]
    My_Team, Opponent = Resolve_Team_Names( Config, Resolved_Metadata )

    print()
    print( f"My Team:                     {My_Team}" )
    print( f"Opponent:                    {Opponent}" )
    print( f"Venue_Name:                  {Resolved_Metadata.get( 'Venue_Name' )}" )
    print( f"Venue_City:                  {Resolved_Metadata.get( 'Venue_City' )}" )
    print( f"Commentary_Pages:            {Commentary_Result[ 'Commentary_Page_Count' ]}" )
    print( f"Commentary_Events:           {len( Commentary_Result[ 'Commentary_Data' ].get( 'commentary', [] ) )}" )
    print( f"Commentary_Duplicates:       {Commentary_Result[ 'Commentary_Duplicate_Count' ]}" )
    print( f"Output:                      {Match_Output_Directory}" )

    Failed_Count = len( Download_Summary.get( "Failed", {} ) )
    Skipped_Count = len( Download_Summary.get( "Skipped", {} ) )

    if ( Failed_Count > 0 ) or ( Skipped_Count > 0 ):
        print( f"ERROR: Download completed with Failed={Failed_Count}, Skipped={Skipped_Count}", file = sys.stderr )

        if ( Failed_Count > 0 ):
            print( "", file = sys.stderr )
            print( "Failed endpoints:", file = sys.stderr )
            for Endpoint_Name, Endpoint_Record in Download_Summary.get( "Failed", {} ).items():
                print(
                    f"  - {Endpoint_Name}: "
                    f"Status={Endpoint_Record.get( 'Status_Code' )} "
                    f"Url={Endpoint_Record.get( 'Url' )}",
                    file = sys.stderr,
                )

        if ( Skipped_Count > 0 ):
            print( "", file = sys.stderr )
            print( "Skipped endpoints:", file = sys.stderr )
            for Endpoint_Name, Endpoint_Record in Download_Summary.get( "Skipped", {} ).items():
                print(
                    f"  - {Endpoint_Name}: "
                    f"Status={Endpoint_Record.get( 'Status_Code' )} "
                    f"Url={Endpoint_Record.get( 'Url' )}",
                    file = sys.stderr,
                )

        print( "", file = sys.stderr )
        print( f"Manifest: {Match_Output_Directory / 'Manifest.json'}", file = sys.stderr )
        return 2

    return 0


#---------------------------------------------------------------------------------------------------------------#
# Main entry point for the MLS Match Data application
# Loads configuration and coordinates match downloading and processing
# Returns the process exit code
#---------------------------------------------------------------------------------------------------------------#
def Main() -> int:
    Arguments = Parse_Arguments()

    try:
        Config = Load_Config()
        Output_Directory = Arguments.output

        if ( Output_Directory is None ):
            Output_Directory = Config[ "Application" ][ "Output_Directory" ]

        print( f"Input_Value:      {Arguments.Input_Value}" )
        print( f"Output_Directory: {Output_Directory}" )

        Session = Create_Session()
        Match_Data = Resolve_Match_Data( Session, Arguments.Input_Value )
        Match_Output_Directory = Build_Output_Directory( Config, Output_Directory, Match_Data )
        Endpoint_Data = Download_Match_Endpoints( Session, Match_Data, Match_Output_Directory )
        Refresh_Resolved_Metadata( Match_Data, Match_Output_Directory )
        Generate_Rosters_CSV( Match_Output_Directory = Match_Output_Directory, My_Team_Names = Config[ "Rosters" ][ "My_Team_Names" ] )
        Commentary_Result = Download_Match_Commentary( Session, Match_Data[ "Match_Id" ], Match_Output_Directory, Endpoint_Data[ "Download_Summary" ] )
        Generate_Match_Outputs( Config, Match_Data, Match_Output_Directory, Endpoint_Data )
        return Print_Match_Summary( Config, Match_Data, Match_Output_Directory, Endpoint_Data, Commentary_Result )

    except Exception as Error:
        print( f"ERROR: {Error}", file = sys.stderr )
        return 1


if ( __name__ == "__main__" ):
    raise SystemExit( Main() )
