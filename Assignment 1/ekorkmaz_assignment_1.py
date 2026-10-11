"""
ASSIGNMENT 1
POKEMON TOURNAMENT

ASSIGNMENT REQUIREMENTS (100 points)
Correctness: import_data 12.5, attack_multiplier 12.5, fight 22.5, tournament 22.5.
Required methods: 5 points per function (20 total; reviewed by the instructor).
Supervised understanding check: 10 points. See the assignment post for details.
Correct output earns correctness credit even if a required method is missing.

AI POLICY AND PERMITTED HELP
Do not use generative AI for any part of this assignment, including generating,
rewriting, debugging, explaining assignment-specific code, or AI autocomplete.
Disable AI coding assistants. Ordinary non-AI editor completion, syntax
highlighting, running Python, and its debugger are allowed. You may use course
materials, official Python documentation, and help from the instructor or TA.
Write your own code; do not copy solutions from classmates, websites, or prior
semesters. Ask the instructor before using a resource not listed here.

SUBMISSION AND EXECUTION
Keep all five function names and parameter lists unchanged. Return results;
do not replace returns with print statements. Do not use input() or run tests
at module level. Put any local test calls under if __name__ == "__main__":.
No imports are needed or permitted in the submitted file for this exercise.
Enter your name and HawkID below. Save as hawkid_assignment_1.py, upload that
file to ICON, and commit and push the identical file to your GitHub repository.
ICON is the graded submission. Identity mistakes will be flagged for correction,
not assigned an automatic zero. The GitHub copy will be checked.

VALID INPUTS AND EDGE CASES
CSV input has no header, no blank lines, and exactly four comma-separated fields
per row. Fields contain no embedded commas or quotes and no surrounding spaces.
The last line may or may not have a newline. An empty file is valid.
Names are nonempty strings. Types are exactly Water, Fire, Electric, Grass, or
Ground. Health and base damage are positive finite numbers. Convert both to
float. No malformed-input handling is required. first2attack is always 1 or 2.
Never change input participant lists, including their health. Every match starts
at the original full health. One attack counts as one round; stop immediately
when either health becomes <= 0 (including exactly zero). Do not round damage
or health. tournament([]) returns []; a one-participant tournament returns [0].
For n participants there are n*(n-1) matches and that many total wins.

Pokemon, also known as Pocket Monsters in Japan, is a Japanese media franchise managed by
The Pokemon Company, a company founded by Nintendo, Game Freak, and Creatures. The franchise
was created by Satoshi Tajiri in 1995, and is centered on fictional creatures called "Pokemon",
which humans, known as Pokemon Trainers, catch and train to battle each other for sport.
Works within the franchise are set in the Pokemon universe. The English slogan for the franchise
is "Gotta Catch 'Em All".

For more information: https://en.wikipedia.org/wiki/Pok%C3%A9mon

In this assignment, we will simulate a Pokemon tournament. Each pokemon will be a
participant in the tournament. In order to simulate, we have 4 main tasks to complete.
Since later tasks are dependent on the prior ones, you have to complete tasks in order.
Explanation of tasks and a pseudocode is provided to you within each function. However,
tasks can be summarized as:
    1. Importing Participant data from a CSV file: Name of the file will be given to you
       as a parameter. This CSV file does not have any header row. It has 4 fields.
            - 1st Field: Name of the Pokemon
            - 2nd Field: Type of the Pokemon ({Water, Fire, Electric, Grass or Ground})
            - 3rd Field: Health (HP) of the Pokemon
            - 4th Field: Base Attack Damage of the Pokemon
    2. Calculating the Attack Multiplier: Since some type of pokemons are more powerful
       against some specific types, their power can be enhanced up to some multiplier value.
       This Attack Multiplier is provided as a chart in the function description below.
    3. Fight Simulation: This task will ask you to implement a fight simulation between two
       given participants/pokemons. You have to use the attack multipliers and find out
       which participant wins the fight after how many rounds.
    4. Tournament Simulation: Since we already implemented the fight simulation between two
       participants, we can easily run a tournament. Each participant will play two games against
       the participants which appears after them in the participants list. We will keep
       track of how many games each participant won in a list, then return this list.
"""

######################################################################
#                           IMPORTANT
# Edit the following function definition, replacing the words
# 'name' with your name and 'hawkid' with your hawkid. If you do not
# change it, the grader will flag your identification for correction.
#
# Note: Your hawkid is the login name you use to access ICON, and NOT
# your firstname-lastname@uiowa.edu email address.
#
# def hawkid():
#     return(["YOUR NAME", "YOUR HAWKID"])
######################################################################

def hawkid():
    return(["ELIF", "EKORKMAZ"])

def import_data(filename):
    """
    This function is used for importing a CSV file to our program
    as a list of lists. Each row will be stored as a list. Therefore,
    in a very high level view:
        - Your CSV file will be stored as a list, where each row
        will be a list inside that list:
        CSV FILE CONTENT: [[ROW1 CONTENT], [ROW2 CONTENT], ...]

    :param filename: This parameter is a string that indicates the
                     filename which we import all the content.
    :return        : This function will return a list of lists, which
                     represents the idea explained above.

    Task Objectives:
    1. Reading a file content
    2. Creating a nested list structure
    3. Type conversion

    Note: Be careful that when you read a file content, even though you read a number,
    its type is interpreted as string (str). Therefore, when you are storing numerical
    values, do not forget to convert its type to float here.
    """
    # REQUIRED METHODS (5 points; 2.5 per numbered item):
    # (1) Use open, a for loop over lines, strip(), and split(",").
    # (2) Use float() for both numbers and append each row to a nested list.
    # Do not use csv, pandas, numpy, or any other imported helper.

    ##### Pseudocode #####
    # 1. Create a list to store all pokemons (MAIN)
    # 2. Open the CSV file with given `filename`
    # 3. Read each line
    #       3.1. Since each line ends with new line, do not forget to strip it
    #       3.2. Store pokemon information in a list (POKEMON):
    #           3.2.1. item of the list should be the name of the pokemon (type: str)
    #           3.2.2. item of the list should be the type of the pokemon (type: str)
    #           3.2.3. item of the list should be the health (HP) of the pokemon (type: float)
    #           3.2.4. item of the list should be the base attack damage of the pokemon (type: float)
    #       3.3. Add -i.e., append- this POKEMON list object to MAIN list object.
    # 4. When you are done with reading all lines & storing the information in a list of lists,
    #    return the MAIN list.
    ######################
    participants = []

    with open(filename, 'r') as file:
      for line in file:
        line = line.strip()
        field = line.split(',')

        participant = [
            field[0],
            field[1],
            float(field[2]),
            float(field[3]) ]

        participants.append(participant)
    return participants

def attack_multiplier(attacker_type, defender_type):
    """
    Attack Multiplier Chart:
        - Water -> Fire (Damage x2.5)
        - Electric -> Water (Damage x1.3)
        - Ground -> Electric (Damage x2)
        - Fire -> Grass (Damage x3)
        - Grass -> Water (Damage x1.5)

    Using the Attack Multiplier Chart above, return the multipliers
    for each attack-defense combination. For example, when
    Attacker type is Water AND Defender type is Fire,
    your function should return 2.5

    For all other attacker-defender combinations, which are not
    given in the Attack Multiplier Chart, your function should
    return 1.0.

    :param attacker_type: This parameter is a string that indicates the
                          type of the attacker.
    :param defender_type: This parameter is a string that indicates the
                          type of the defender.
    :return             : This function will return a float value, which
                          represents the attack multiplier for given
                          combination.

    Task Objectives:
    1. Using if conditions for decision making
    2. Combining several condition statements into one
    """
    # REQUIRED METHODS (5 points; 2.5 per numbered item):
    # (1) Use if/elif/else with and to check attacker-defender combinations.
    # (2) Implement all five special cases and the default in that chain;
    #     do not use a dictionary or other lookup table.

    ##### Pseudocode #####
    # 1. If Attacker is Water and Defender is Fire, return 2.5
    # 2. Else if Attacker is Electric and Defender is Water, return 1.3
    # 3. Else if Attacker is Ground and Defender is Electric, return 2.0
    # 4. Else if Attacker is Fire and Defender is Grass, return 3.0
    # 5. Else if Attacker is Grass and Defender is Water, return 1.5
    # 6. Else, return 1.0
    ######################

    if attacker_type == 'Water' and defender_type == 'Fire':
      return 2.5
    elif attacker_type == 'Electric' and defender_type == 'Water':
      return 1.3
    elif attacker_type == 'Ground' and defender_type == 'Electric':
      return 2.0
    elif attacker_type == 'Fire' and defender_type == 'Grass':
      return 3.0
    elif attacker_type == 'Grass' and defender_type == 'Water':
      return 1.5

    else:
      return 1.0

def fight(participant1, participant2, first2attack):
    """
    This function simulates a fight between two participants, where who will
    attack first is determined by the first2attack parameter. You can safely
    assume that there will be no tie/draw situation.

    :param participant1: This parameter is a list that indicates the
                         information about the first participant. List
                         content and the item order is the same as explained
                         in the import_data function.
                         List contains 4 items:
                            1. Name of the Pokemon (type: str)
                            2. Type of the Pokemon (type: str)
                            3. Health (HP) of the Pokemon (type: float)
                            4. Base Attack Damage of the Pokemon (type: float)
    :param participant2: This parameter is a list that indicates the
                         information about the second participant. List
                         content and the item order is the same as explained
                         in the import_data function.
                         List contains 4 items:
                            1. Name of the Pokemon (type: str)
                            2. Type of the Pokemon (type: str)
                            3. Health (HP) of the Pokemon (type: float)
                            4. Base Attack Damage of the Pokemon (type: float)
    :param first2attack: This parameter is an integer that indicates which
                         participant attacks first. If the value is 1,
                         participant1 will attack first. If the value is 2, participant2
                         will attack.
    :return            : This function will return a list of integers. First item of
                         the list will be the winner index (1 or 2), the second
                         item will be the number of rounds of the fight. Each attack
                         is counted as a round, independent from who is the attacker or
                         the defender.

    Task Objectives:
    1. Storing a value in a different variable, and reassigning it
    2. Using while loop and figuring out the condition for the loop
    3. Taking different actions according to a value of a parameter
    4. Calling another function inside a function.
    """
    # REQUIRED METHODS (5 points; 2.5 per numbered item):
    # (1) Use a while loop with one attack per iteration; alternate attackers.
    # (2) Call attack_multiplier and update local health variables without
    #     modifying either input list. A direct round-count formula is not allowed.

    ##### Pseudocode #####
    # 1. Initialize rounds variable:
    #    - rounds = 0
    # 2. Store the initial health of both participants in two variables.
    #    - variable1 = HP of the first participant
    #    - variable2 = HP of the second participant
    # 3. While both of the healths (use variable1 and variable2) are greater than 0: (i.e., None of the pokemons is dead)
    #       3.1. If first to attack is 1:
    #           3.1.1. Find the attack multiplier where the attacker type is the type
    #                  of the first pokemon, and the defender type is the type of the
    #                  second pokemon. (Hint: You should call attack_multiplier function)
    #           3.1.2. Calculate new attack damage by multiplying the attack multiplier with
    #                  the first pokemon's base attack damage.
    #           3.1.3. Subtract new attack damage from the second participant's health
    #       3.2. Else if first to attack is 2 (or Else):
    #           3.2.1. Find the attack multiplier where the attacker type is the type
    #                  of the second pokemon, and the defender type is the type of the
    #                  first pokemon. (Hint: You should call attack_multiplier function)
    #           3.2.2. Calculate new attack damage by multiplying the attack multiplier with
    #                  the second pokemon's base attack damage.
    #           3.2.3. Subtract new attack damage from the first participant's health
    #       3.3. Increment the rounds variable by one.
    #       3.4. Toggle first2attack variable. (If it is 1, make it 2. If it is 2, make it 1.)
    # 4. If variable1 is greater than 0, then winner is 1. However, if variable 2 is greater than 0,
    #    then winner is 2.
    # 5. Return [winner, rounds]
    ######################
    rounds  = 0
    winner  = 1

    variable1 = participant1[2]
    variable2 = participant2[2]

    while variable1 > 0 and variable2 > 0:
      if first2attack == 1:
        multiplier = attack_multiplier(participant1[1], participant2[1])
        new_attack_damage = multiplier * participant1[3]
        variable2 = variable2 - new_attack_damage

      elif first2attack == 2:
        multiplier = attack_multiplier(participant2[1], participant1[1])
        new_attack_damage = multiplier * participant2[3]
        variable1 = variable1 - new_attack_damage

      rounds += 1
      first2attack = 3 - first2attack

    if variable1 > 0:
      winner = 1
    else:
      winner = 2

    return [winner, rounds]

def tournament(participants):
    """
    This function simulates a tournament between a list of participants.
    Tournament works as follows:
        - Each participant fights two matches against all the participants
          that come after them in the list. One of these matches is a
          'home' game, where first participant is first one to attack,
          i.e., 3rd parameter of the fight function call should be 1.
          Second game will be an 'away' game, where the second participant
          is first one to attack, i.e., 3rd parameter of the fight function
          call should be 2.
        - How many games each participant won will be stored in a list. For example,
          if there are 4 participants and they won 3, 3, 3, 3 games respectively. Thus,
          your wins list should be [3, 3, 3, 3].

    :param participants: This parameter is a list of lists that indicates the
                         stores the information of each participant as a list. The
                         content and the item order is the same as explained
                         in the import_data function. High level view of data can be:

                            - PARTICIPANTS = [[Name1, Type1, HP1, DMG1], [Name2, Type2, HP2, DMG2], ...]

                         Participant info list contains 4 items:
                            1. Name of the Pokemon (type: str)
                            2. Type of the Pokemon (type: str)
                            3. Health (HP) of the Pokemon (type: float)
                            4. Base Attack Damage of the Pokemon (type: float)
    :return            : This function will return a list of integers. Each integer will
                         represent how many games that corresponding participant won. In other words,
                         First item of the list will tell how many games first participant won, second
                         item of the list will tell how many games second participant won, and so on...

    Task Objectives:
    1. Generating a list of integer and manipulating it according to results
    2. Using a nested for loop structure
    3. Calling another function inside a function with different parameter values.
    """
    # REQUIRED METHODS (5 points; 2.5 per numbered item):
    # (1) Use nested for loops over participant indices with j > i.
    # (2) Call fight twice per pair (starting attackers 1 and 2), and use
    #     each result to increment the corresponding participant's win count.

    ##### Pseudocode #####
    # 1. Initialize the list (WINS) where we will store how many games won by each participant.
    #    Note that the list should contain all 0s for each participant. For example, if
    #    we have 5 participants, our list should be [0, 0, 0, 0, 0].
    # 2. For each participant: (starting from first participant, until the last one)
    #       2.1. For each remaining participant in the list: (starting from (the index of first participant) + 1, until the last one)
    #           2.1.1. Play a home game. Call fight function and pass 1 as the third parameter
    #           2.1.2. Play an away game. Call fight function and pass 2 as the third parameter
    #           2.1.3. Check results for home and away games:
    #                   2.1.3.1. If winner of the game is first participant, use first participant's index
    #                            to increment the number of wins of first participant in the WINS list.
    #                   2.1.3.2. However, if the winner is second participant, use second participant's index
    #                            to increment the number of wins of second participant in the WINS list.
    # 3. Return WINS list
    ######################
    wins = []

    for x in range(len(participants)):
      wins.append(0)

    for x in range(len(participants)):
      for y in range(x + 1, len(participants)):
        home = fight(participants[x], participants[y], 1)
        away = fight(participants[x], participants[y], 2)

        if home[0] == 1:
          wins[x] += 1
        else:
          wins[y] += 1

        if away[0] == 1:
          wins[x] += 1
        else:
          wins[y] += 1

    return wins


