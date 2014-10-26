#!/usr/bin/python3

from collections import defaultdict
import copy
import csv
import random
import string
import sys

SWITCHING_ROLE_PENALTY = .1
ALREADY_BOOKED_BENEFIT = .2
HELPTEXT = '''Call like: ./beatrice.py /path/to/actors.csv /path/to/cast.csv /path/to/unavailable.txt
\nWhere actors.csv (one for all dates) is a CSV file like
  Name,Role,Skill,Convenience

  AnActor,      ARole,      .5,     .5
  AnotherActor, ARole,      .8,     .6
  ...
\nAnd cast.csv (one for each date) is a CSV file like
  Role,Name

  Role,                  ActorBookedForRole
  UnbookedRole
  AnotherUnbookedRole
  ...
\nAnd unavailable.txt (one for each date) is a text file like
  UnavailableActor
  AnotherUnavailableActor'''

# Scores a cast, based on how convenient it would be to schedule each
# actor for each role and how good each actor is at each role.
# TWEAK ME!
def ScoreCast(cast, role_actor_convenience, role_actor_skill):
  score = 1
  for role in cast:
    actor = cast[role]
    convenience = role_actor_convenience[role][actor]
    skill = role_actor_skill[role][actor]
    score *= convenience * skill
  return score

# Check if a potential cast has all the actors in the supplied list.
# Useful to make sure to include actors who have already
# been scheduled. The actors need not appear in their originally
# booked roles, they just have to be present in some role.
def CastHasRequiredActors(cast, required_actors):
  for actor in required_actors:
    if actor not in list(cast.values()):
      return False;
  return True;

# Returns the next role with no assigned actor.
def NextUnfilledRole(cast):
  for role in cast:
    if cast[role] is None:
      return role
  return None

# Given a map (role)->(actors who can play that role), removes
# an actor from all such lists. This is useful if the actor has
# been potentially assigned to another role.
def CopyPurgingActor(role_actor, actor):
  role_actor_copy = copy.deepcopy(role_actor)
  for role in role_actor_copy:
    if actor in role_actor_copy[role]:
      role_actor_copy[role].remove(actor)
  return role_actor_copy

# Recursive function! Gulp. Works in two parts:
# 1. "Base case." The function receives a full cast. After verifying
# that all actors who are already booked are present in this cast,
# returns the cast.
# 2. "Inductive case." The function receives a cast missing at least
# one role. In that case, generates all possible actor assignments 
# for that role, based on the supplied list 'role_actor' of actors who
# can play that role. Then calls itself on EACH of these new potential
# casts.
# Guaranteed to terminate since (a) termination condition is "zero
# unassigned roles", (b) each iteration reduces the number of
# unassigned roles by 1, and (c) the starting number of unassigned
# roles must be a positive, finite integer.
def GeneratePossibleCasts(cast, role_actor, scheduled_actors):
  role = NextUnfilledRole(cast)
  possible_casts = []
  if role is None:
    # Base case. Cast is full.
    if CastHasRequiredActors(cast, scheduled_actors):
      possible_casts.append(cast)
  else:
    # Inductive case. Expand the tree of possible casts.
    actors = role_actor[role]
    for actor in actors:
      cast_copy = copy.deepcopy(cast)
      cast_copy[role] = actor
      role_actor_copy = CopyPurgingActor(role_actor, actor)
      possible_casts.extend(
        GeneratePossibleCasts(cast_copy, role_actor_copy, scheduled_actors))
  return possible_casts

def main(argv=sys.argv):
  if len(argv) != 4:
    print(HELPTEXT)
    return 1

  # Read in the cast, with all actors who have already been scheduled.

  cast_reader = csv.DictReader(open(sys.argv[2]))
  current_cast = {}
  actor_current_role = {}
  scheduled_actors = []
  for entry in cast_reader:
    role = entry['Role'].strip()
    actor = entry['Name']
    if actor is not None:
      actor = actor.strip()
    if actor == '':
      actor = None
    current_cast[role] = actor
    actor_current_role[actor] = role
    if actor is not None:
      scheduled_actors.append(actor)

  # Read in the list of actors known to be unavailable.

  unavailable_actors = []
  with open(sys.argv[3], 'r') as unavailable_file:
    for line in unavailable_file.readlines():
      actor = line.strip()
      if line is not '':
        unavailable_actors.append(actor)

  # Read in the actor database.

  actor_reader = csv.DictReader(open(sys.argv[1]))
  # A map of actor -> how convenient it is to book that actor.
  actor_convenience = {}
  # A map of actor -> entry containing the convenience score.
  # Used only to validate input.
  actor_convenience_entries = {}
  # A map of roles -> list of actors who can play that role.
  role_actors = defaultdict(list)
  # A nested map! (role) -> (actor who can play that role) -> (skill)
  role_actor_skill = defaultdict(lambda : defaultdict(float))
  for entry in actor_reader:
    actor = entry['Name'].strip()
    role = entry['Role'].strip()
    try:
      skill = float(entry['Skill'].strip())
    except ValueError:
      print('Error parsing entry %s' % entry)
      return 1
    convenience_str = entry['Convenience']
    if convenience_str is not None and convenience_str.strip() != '':
      try:
        convenience = float(convenience_str.strip())
      except ValueError:
        print('Error parsing entry %s' % entry)
        return 1
      # Check for a bunch of possible errors, then add convenience to the map.
      if actor in actor_convenience:
        # Not every row needs to specify a 'convenience' factor, just one.
        # Error if multiple convenience factors found.
        print('Error! Convenience scores found for %s in two entries. '
              'Only use one.\nOffending Entries:\n%s\n%s' %
              (actor, actor_convenience_entries[actor], entry))
        return 1
      if convenience == 0:
        print('Error! Convenience score is 0. Typo here?\n%s' % entry)
        return 1
      actor_convenience[actor] = convenience
      actor_convenience_entries[actor] = entry  # Only for input validation.
    if actor in unavailable_actors:
      print('%s is unavailable for %s.' % (actor, role))
      continue
    if role not in current_cast:
      print('%s not needed for %s.' % (actor, role))
      continue
    if skill == 0:
      print('Error! Skill score is 0. Typo here?\n%s' % entry)
      return 1
    if actor in role_actor_skill[role]:
      print('Error! %s listed twice for %s' % (actor, role))
      return 1
    role_actor_skill[role][actor] = skill
    role_actors[role].append(actor)

  # Validate cast.csv file, make sure nobody is assigned to a role they don't
  # play and that every role exists.
  for role in current_cast:
    if role not in role_actors:
      print('Error! Found role %s in cast.csv file, but not in actors.csv '
            'database.' % role)
      return 1
    actor = current_cast[role]
    if actor is None:
      continue
    if actor not in role_actor_skill[role]:
      print('Error! %s assigned to play %s, '
            'but has no such entry in the actors.csv database.' %
            (actor, role))
      return 1

  # Validate unavailable.txt file, make sure every actor mentioned has an entry
  # in the actors.csv database.
  for actor in unavailable_actors:
    if actor not in actor_convenience:
      print('Error! %s marked as unavailable, but is not present in actors.csv '
            'database.' % actor)
      return 1

  # A nested map! (role) -> (actor who can play that role) -> (convenience).
  # Start with the actor's "base" convenience. Then add a bonus if the actor is
  # already booked for a particular role, or subtract a penalty if a *different*
  # actor is already booked for a particular role and would need to be moved.
  role_actor_convenience = defaultdict(lambda : defaultdict(float))
  for role in role_actor_skill:
    for actor in role_actor_skill[role]:
      if actor not in actor_convenience:
        print('Error! Found no convenience score for \'%s\'' % actor)
        return 1
      convenience = actor_convenience[actor]
      if current_cast[role] is None:
        role_actor_convenience[role][actor] = convenience
      elif current_cast[role] == actor:
        # The actor is already booked in this role, add a benefit for not needing
        # to do anything.
        role_actor_convenience[role][actor] = convenience + ALREADY_BOOKED_BENEFIT
      else:
        # Somebody else is cast in this role, add a penalty for needing to
        # reassign the other actor.
        role_actor_convenience[role][actor] = convenience - SWITCHING_ROLE_PENALTY

  # Generate all possible casts based on above databases.

  blank_cast = {}
  for role in current_cast:
    blank_cast[role] = None
  possible_casts = GeneratePossibleCasts(blank_cast, role_actors, scheduled_actors)
  if len(possible_casts) == 0:
    print('No possible casts! Try being more flexible in actors.csv')
    return 1

  # Score all of the casts.
  scored_casts = []
  scores = []
  for cast in possible_casts:
    score_for_cast = ScoreCast(cast, role_actor_convenience, role_actor_skill)
    scored_casts.append((cast, score_for_cast))
    scores.append(score_for_cast)
  scored_casts.sort(key=lambda x: x[1], reverse=True)
  scores.sort(reverse=True)

  # Choose a cast at random, weighted by score.
  running_total = 0
  rand = random.uniform(0, sum(scores))
  for potential_cast, score in scored_casts:
    running_total += score
    if running_total > rand:
      random_cast = potential_cast
      random_cast_score = score
      break
  best_cast = scored_casts[0][0]

  # Print random cast, side by side with best.
  # To do this, write a three-column table, then print row-by-row.
  cast_matrix = [['ROLES', 'RANDOM CAST', 'BEST CAST']]
  for role in sorted(random_cast):
    row = [role]
    random_actor = random_cast[role]
    if random_actor in actor_current_role:
      if role != actor_current_role[random_actor]:
        random_actor += ' (reassigned from %s)' % actor_current_role[random_actor]
    row.append(random_actor)

    best_actor = best_cast[role]
    if best_actor in actor_current_role:
      if role != actor_current_role[best_actor]:
        best_actor += ' (reassigned from %s)' % actor_current_role[best_actor]
    row.append(best_actor)
    cast_matrix.append(row)

  rank = scores.index(score)
  rank += 1  # Correct zero-indexing.  
  print('\nRandom Cast ranks %d out of %d, scoring %d%% of Best' %
        (rank, len(scores), score * 100 / scores[0]))

  # Reorganize data by columns
  cols = zip(*cast_matrix)
  # Compute column widths by taking maximum length of values per column
  col_widths = [ max(len(value) for value in col) + 2 for col in cols ]
  # Create a suitable format string
  format = ' '.join(['%%%ds' % width for width in col_widths ])
  
  for row in cast_matrix:
    print(format % tuple(row))
  return 0

if __name__ == "__main__":
    sys.exit(main())
