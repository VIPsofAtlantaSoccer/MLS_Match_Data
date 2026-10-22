#---------------------------------------------------------------------------------------------------------------#
# py -m pip install --upgrade package_name
#---------------------------------------------------------------------------------------------------------------#

#---------------------------------------------------------------------------------------------------------------#
# Read roster JSON files and output players in shirt-number order
#
# What it does:
#   - Reads two roster JSON files
#   - Detects which roster is Atlanta United
#   - Assigns prefix "a" to Atlanta players and "o" to opponent players
#   - Sorts players by shirt number
#   - Outputs lines in the format:
#         {a/o}##    {last_name}
#
# Example:
#   a01    Hoyos
#   o14    Sejdić
#
# Notes:
#   - Shirt numbers are zero-padded to 2 digits
#   - If a player does not have a valid shirt number, that player is skipped
#---------------------------------------------------------------------------------------------------------------#

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Example Usage
# python Get_MLS_Rosters.py "Roster - Atlanta United.json" "Roster - Columbus Crew.json"
# python Get_MLS_Rosters.py "Roster - Atlanta United.json" "Roster - Columbus Crew.json" -output Rosters.csv

ATLANTA_NAMES = [
    "atlanta united",
    "atlanta united fc",
    "atl utd",
    "atlutd",
    "atlanta united 2",
    "atlutd2",
]


#---------------------------------------------------------------------------------------------------------------#
# Force UTF-8 output so player names with accents do not fail on Windows
# Returns nothing
#---------------------------------------------------------------------------------------------------------------#
def Configure_Output_Encoding() -> None:
    if hasattr( sys.stdout, "reconfigure" ):
        sys.stdout.reconfigure( encoding = "utf-8" )

    if hasattr( sys.stderr, "reconfigure" ):
        sys.stderr.reconfigure( encoding = "utf-8" )

#---------------------------------------------------------------------------------------------------------------#
# Read a JSON file from disk
# Returns the parsed JSON dictionary
#---------------------------------------------------------------------------------------------------------------#
def Read_Json_File( File_Path: Path ) -> Dict[str, Any]:
    with File_Path.open( "r", encoding = "utf-8" ) as File_Handle:
        Data = json.load( File_Handle )

    if not isinstance( Data, dict ):
        raise RuntimeError( f"JSON file is not a dictionary: {File_Path}" )

    return Data


#---------------------------------------------------------------------------------------------------------------#
# Determine the club name from a roster JSON payload
# Returns the club name string, or an empty string if not found
#---------------------------------------------------------------------------------------------------------------#
def Get_Club_Name( Roster_Data: Dict[str, Any] ) -> str:
    Players = Roster_Data.get( "players", [] )

    if not isinstance( Players, list ):
        return ""

    for Player in Players:
        if not isinstance( Player, dict ):
            continue

        Club_Name = Player.get( "club_name", "" )

        if isinstance( Club_Name, str ) and Club_Name.strip():
            return Club_Name.strip()

    return ""


#---------------------------------------------------------------------------------------------------------------#
# Convert one roster JSON payload into formatted output rows
# Returns a list of tuples: ( shirt_number, output_line )
#---------------------------------------------------------------------------------------------------------------#
def Build_Roster_Lines( Roster_Data: Dict[str, Any], Prefix: str ) -> List[Tuple[int, str]]:
    Output_Lines: List[Tuple[int, str]] = []
    Players = Roster_Data.get( "players", [] )

    if not isinstance( Players, list ):
        return Output_Lines

    for Player in Players:
        if not isinstance( Player, dict ):
            continue

        Shirt_Number = Player.get( "shirt_number" )
        Last_Name = Player.get( "last_name", "" )

        if not isinstance( Shirt_Number, int ):
            continue

        if not isinstance( Last_Name, str ):
            continue

        Last_Name = Last_Name.strip()

        if not Last_Name:
            continue

        #Output_Line = f"{Prefix}{Shirt_Number:02d}\t{Last_Name}"
        Output_Line = f"{Prefix}{Shirt_Number:02d},{Last_Name}"
        Output_Lines.append( ( Shirt_Number, Output_Line ) )

    Output_Lines.sort( key = lambda Item: Item[ 0 ] )

    return Output_Lines


#---------------------------------------------------------------------------------------------------------------#
# Determine which roster is Atlanta and which is the opponent
# Returns a tuple: ( Atlanta_Roster_Data, Opponent_Roster_Data )
#---------------------------------------------------------------------------------------------------------------#
def Resolve_Rosters(
    First_Roster_Data: Dict[str, Any],
    Second_Roster_Data: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:

    First_Club_Name = Get_Club_Name( First_Roster_Data )
    Second_Club_Name = Get_Club_Name( Second_Roster_Data )

    First_Is_Atlanta = First_Club_Name.strip().lower() in ATLANTA_NAMES
    Second_Is_Atlanta =  Second_Club_Name.strip().lower() in ATLANTA_NAMES

    if ( First_Is_Atlanta ) and ( not Second_Is_Atlanta ):
        return First_Roster_Data, Second_Roster_Data

    if ( Second_Is_Atlanta ) and ( not First_Is_Atlanta ):
        return Second_Roster_Data, First_Roster_Data

    raise RuntimeError(
        "Could not uniquely determine Atlanta United roster.\n"
        f"First roster club:  {First_Club_Name}\n"
        f"Second roster club: {Second_Club_Name}"
    )

#---------------------------------------------------------------------------------------------------------------#
# Write output lines to a text file
# Returns nothing
#---------------------------------------------------------------------------------------------------------------#
def Write_Output_File( File_Path: Path, Output_Lines: List[str] ) -> None:
    with File_Path.open( "w", encoding = "utf-8" ) as File_Handle:
        for Line in Output_Lines:
            File_Handle.write( f"{Line}\n" )


#---------------------------------------------------------------------------------------------------------------#
# Main entry point
# Returns process exit code
#---------------------------------------------------------------------------------------------------------------#
def Main() -> int:
    Configure_Output_Encoding()

    Parser = argparse.ArgumentParser(
        description = "Read two MLS roster JSON files and output shirt-number mappings"
    )

    Parser.add_argument(
        "First_Roster_File",
        help = "Path to the first roster JSON file"
    )

    Parser.add_argument(
        "Second_Roster_File",
        help = "Path to the second roster JSON file"
    )

    Parser.add_argument(
        "-output",
        help = "Optional text output file"
    )

    Arguments = Parser.parse_args()

    try:
        First_Roster_Path = Path( Arguments.First_Roster_File )
        Second_Roster_Path = Path( Arguments.Second_Roster_File )

        First_Roster_Data = Read_Json_File( First_Roster_Path )
        Second_Roster_Data = Read_Json_File( Second_Roster_Path )

        Atlanta_Roster_Data, Opponent_Roster_Data = Resolve_Rosters(
            First_Roster_Data = First_Roster_Data,
            Second_Roster_Data = Second_Roster_Data,
        )

        Atlanta_Lines = Build_Roster_Lines(
            Roster_Data = Atlanta_Roster_Data,
            Prefix = "a",
        )

        Opponent_Lines = Build_Roster_Lines(
            Roster_Data = Opponent_Roster_Data,
            Prefix = "o",
        )

        Output_Lines = [ Item[ 1 ] for Item in Atlanta_Lines ]
        Output_Lines.extend( [ Item[ 1 ] for Item in Opponent_Lines ] )

        for Line in Output_Lines:
            print( Line )

        if Arguments.output:
            Output_File_Path = Path( Arguments.output )
            Write_Output_File(
                File_Path = Output_File_Path,
                Output_Lines = Output_Lines,
            )
            print()
            print( f"Wrote output file: {Output_File_Path}" )

        return 0

    except Exception as Error:
        print( f"ERROR: {Error}", file = sys.stderr )
        return 1


if __name__ == "__main__":
    raise SystemExit( Main() )
