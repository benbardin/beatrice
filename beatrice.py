#! /usr/bin/env python3

from collections import defaultdict
import copy
import csv
import datetime
import random
import re
import sys

# Only consider casts at least as good as this fraction * the 'best' cast.
SWITCHING_ROLE_PENALTY = .1
ALREADY_BOOKED_BENEFIT = .2
HELPTEXT = '''Call like:
./beatrice.py /path/to/actors.csv /path/to/cast.csv /path/to/unavailable.txt SHOWTIME
\nWhere actors.csv (one for all dates) is a CSV file like
  Name,Role,Skill,Convenience

  AnActor,      ARole,      .5,     .5
  AnotherActor, ARole,      .8,     .6
  ...
\nAnd cast.csv (one for each date) is a CSV file like
  Role,RelativeCallTime,Name

  Role,                  , 2,    ActorBookedForRole
  UnbookedRole           , -:30,
  AnotherUnbookedRole    , 1:30,
  ...
\nAnd unavailable.txt (one for each date) is a text file like
  UnavailableActor
  AnotherUnavailableActor

\nAnd SHOWTIME looks like "3:00PM", "3PM", or "15:00"'''

# Scores a cast, based on how convenient it would be to schedule each
# actor for each role and how good each actor is at each role.
# TWEAK ME!
def ScoreCast(cast, role_actor_convenience, role_actor_skill):
  score = 1
  empty_cast = True  # For an empty cast, return a score of 0 later.
  for role in cast:
    actor = cast[role]
    if actor is not None:
      empty_cast = False
      convenience = role_actor_convenience[role][actor]
      skill = role_actor_skill[role][actor]
      score *= convenience * skill
  if empty_cast:
    return 0
  else:
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
  empty_roles = []
  for role in cast:
    if cast[role] is None:
      empty_roles.append(role)
  if empty_roles:
    return sorted(empty_roles)[0]
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
def GeneratePossibleCasts(cast,
                          role_actor,
                          scheduled_actors,
                          best_score,
                          role_actor_convenience,
                          role_actor_skill):
  role = NextUnfilledRole(cast)
  possible_casts = []
  if role is None:
    # Base case. Cast is full.
    if CastHasRequiredActors(cast, scheduled_actors):
      possible_casts.append(cast)
      best_score = max(best_score,
                       ScoreCast(cast, role_actor_convenience, role_actor_skill))
  else:
    # Inductive case. Expand the tree of possible casts.
    actors = role_actor[role]
    actor_convenience = role_actor_convenience[role]
    actor_skill = role_actor_convenience[role]
    actors.sort(
      key=lambda actor: actor_convenience[actor] * actor_skill[actor],
      reverse=True)
    for actor in actors:
      cast_copy = copy.deepcopy(cast)
      cast_copy[role] = actor
      if ScoreCast(cast_copy,
                   role_actor_convenience,
                   role_actor_skill) < best_score:
        continue
      role_actor_copy = CopyPurgingActor(role_actor, actor)
      children = GeneratePossibleCasts(cast_copy,
                                       role_actor_copy,
                                       scheduled_actors,
                                       best_score,
                                       role_actor_convenience,
                                       role_actor_skill)
      possible_casts.extend(children[0])
      best_score = max(best_score, children[1])
  return (possible_casts, best_score)

def timeOfDay(timeString):
  try:
    return datetime.datetime.strptime(timeString, '%I:%M%p')
  except ValueError:
    pass
  try:
    return datetime.datetime.strptime(timeString, '%H:%M')
  except ValueError:
    pass
  try:
    return datetime.datetime.strptime(timeString, '%I%p')
  except ValueError:
    pass

def timeDelta(timeString):
  groups = re.search('(-)?(\d?\d)?:?(\d\d)?', timeString).groups()
  h_m = [int(x) if x else 0 for x in groups[1:]]
  if groups[0]:
    h_m[0] *= -1
  return datetime.timedelta(hours=h_m[0], minutes = h_m[1])

def shortFormatTime(time, space=True):
  if space:
    timeString = time.strftime('%I:%M %p')
  else:
    timeString = time.strftime('%I:%M%p')
  timeString = re.sub(':00', '', timeString)
  if timeString[0] == '0':
    timeString = timeString[1:]
  return timeString

def main(argv=sys.argv):
  if len(argv) != 5:
    print(HELPTEXT)
    return 1

  # Read in the cast, with all actors who have already been scheduled.

  cast_reader = csv.DictReader(open(sys.argv[2]))
  current_cast = {}
  actor_current_role = {}
  scheduled_actors = []
  cast_order = []
  showtime = timeOfDay(sys.argv[4])
  call_times = {}
  if showtime is None:
    print('Showtime is in a bad format.')
    return 1

  show_tag_matcher = re.compile('\[.*\]')
  for entry in cast_reader:
    role = entry['Role'].strip()
    cast_order.append(role)
    if show_tag_matcher.match(role):
      continue

    actor = entry['Name']
    if actor is not None:
      actor = actor.strip()
    if actor == '':
      actor = None
    current_cast[role] = actor
    actor_current_role[actor] = role
    if actor is not None:
      scheduled_actors.append(actor)

    relative_calltime = entry['CallTime']
    if relative_calltime is None:
      print('Need call time for role %s' % role)
      return 1
    relative_calltime = relative_calltime.strip()
    calltime = showtime + timeDelta(relative_calltime)
    call_times[role] = calltime

  # Read in the list of actors known to be unavailable.
  unavailable_actors = []
  with open(sys.argv[3], 'r') as unavailable_file:
    for line in unavailable_file.readlines():
      actor = line.strip()
      print('%s is unavailable.' % actor)
      if actor != '':
        unavailable_actors.append(actor)

  # Read in the actor database.

  actor_reader = csv.DictReader(open(sys.argv[1]))
  # A map of actor -> how convenient it is to book that actor.
  actor_convenience = {}
  # A map of actor -> original entry containing the convenience score.
  # Used only to print helpful messages if contradictory information is found.
  actor_entries = {}
  # A map of roles -> list of actors who can play that role.
  role_actors = defaultdict(list)
  # A nested map! (role) -> (actor who can play that role) -> (skill)
  role_actor_skill = defaultdict(lambda : defaultdict(float))
  # Used to validate unavailable.txt file. Every unavailable actor should be
  # mentioned in the database.
  unavailable_actors_with_entries = set()
  for entry in actor_reader:
    actor = entry['Name'].strip()
    role = entry['Role'].strip()
    skill_str = entry['Skill'].strip()
    convenience_str = entry['Convenience']
    if '' == actor == role == skill_str == convenience_str:
      continue
    try:
      skill = float(skill_str)
    except ValueError:
      print('Error parsing entry %s' % entry)
      return 1
    if actor in unavailable_actors:
      unavailable_actors_with_entries.add(actor)
      continue
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
              (actor, actor_entries[actor], entry))
        return 1
      if convenience == 0:
        print('Error! Convenience score is 0. Typo here?\n%s' % entry)
        return 1
      actor_convenience[actor] = convenience
      actor_entries[actor] = entry  # Only for input validation.
    if role not in current_cast:
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
    if actor not in unavailable_actors_with_entries:
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
      convenience *= 1 - (ALREADY_BOOKED_BENEFIT + SWITCHING_ROLE_PENALTY)
      convenience += SWITCHING_ROLE_PENALTY
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
  possible_casts, best_score = GeneratePossibleCasts(blank_cast, role_actors, scheduled_actors, 0, role_actor_convenience, role_actor_skill)
  if len(possible_casts) == 0:
    print('No possible casts! Try being more flexible in actors.csv')
    return 1

  # Score all of the casts.
  scored_casts = []
  for cast in possible_casts:
    score_for_cast = ScoreCast(cast, role_actor_convenience, role_actor_skill)
    scored_casts.append((cast, score_for_cast))
  scored_casts.sort(key=lambda x: x[1], reverse=True)
  best_cast = scored_casts[0][0]

  cast_matrix = [['ROLES', 'CALL TIME', 'CAST',]]
  for role in cast_order:
    row = [role]
    if show_tag_matcher.match(role):
      row.extend(['-', '-'])
    else:
      row.append(shortFormatTime(call_times[role]))
      best_actor = best_cast[role]
      if best_actor in actor_current_role:
        if role != actor_current_role[best_actor]:
          best_actor += ' (reassigned from %s)' % actor_current_role[best_actor]
      row.append(best_actor)
    cast_matrix.append(row)

  # Add unassigned actors
  unused_actors_best_cast = []
  unused_actors_random_cast = []
  for actor in actor_convenience:
    if actor not in best_cast.values():
      unused_actors_best_cast.append(actor)

  if len(unused_actors_best_cast) > 0:
    cast_matrix.append(['', '', ''])
    cast_matrix.append(['[UNASSIGNED]', '-', '-'])
  for i in range(0, len(unused_actors_best_cast)):
    cast_matrix.append(['-', '-', unused_actors_best_cast[i]])

  # Reorganize data by columns
  cols = zip(*cast_matrix)
  # Compute column widths by taking maximum length of values per column
  col_widths = [ max(len(value) for value in col) + 2 for col in cols ]
  # Create a suitable format string
  format = ' '.join(['%%%ds' % width for width in col_widths ])

  print('')
  for row in cast_matrix:
    print(format % tuple(row))

  print('\nEmail-able lines:\n')
  for role in cast_order:
    if show_tag_matcher.match(role):
      print(role)
    else:
      print('%s: %s, %s' % (role, best_cast[role], shortFormatTime(call_times[role], space=False)))

  return 0

if __name__ == "__main__":
    sys.exit(main())
