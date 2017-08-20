import glob
import logging
import os
import sys
import re
import csv

log_dir = "logs"
global_identifier = "assignments-itc-f17"

incoming_assignments_folder = os.path.join("..", "db-sim", global_identifier)

current_timestamp = '0'

def touch(fname, times=None):
    with open(fname, 'a'):
        os.utime(fname, times)

def get_current_timestamp():
  import datetime, time
  ts = time.time()
  st = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d-%H%M%S')
  return st

def set_logging_params(tag):
  global current_timestamp
  current_timestamp = get_current_timestamp()
  log_file = os.path.join(log_dir, tag + "-" + current_timestamp + ".log")
  print "Output to log: " + log_file

  if not os.path.exists(log_dir):
    logging.debug("Creating logs directory: " + log_dir)
    os.makedirs(log_dir)

  logging.basicConfig(format='%(asctime)s [%(levelname)7s] %(message)s', filename=log_file, level=logging.DEBUG)
  # logging.basicConfig(format='%(asctime)s [%(levelname)7s] %(message)s', level=logging.DEBUG)

  logging.debug("Writing logs now.")

def get_student_ids(incoming_folder):
  logging.debug("Getting student IDs from: " + incoming_folder )
  student_paths = glob.glob(os.path.join(incoming_folder, '*'))
  student_ids = [os.path.basename(os.path.normpath(x)) for x in student_paths]
  return student_ids

def get_assignment_config(tag, global_identifier):
  import json
  config_path = os.path.join(global_identifier, tag, 'config.json')
  with open(config_path) as data_file:
    data = json.load(data_file)

  logging.debug("Loaded assignment config: " + str(data))
  return data


def write_student_log(student_assignment_folder, outlog):
  out_file = os.path.join(student_assignment_folder, "test-results-" + current_timestamp + ".log")
  logging.debug("Writing log to: " + out_file)
  with open(out_file, "a") as text_file:
    text_file.write(outlog)

def get_score_from_result_line(res_line, total_points):
  # case where we have failures and passes
  match = re.match(r"=*\s(\d*)\sfailed,\s(\d*)\spassed\s.*", res_line)
  if match:
    failed = int(match.group(1))
    passed = int(match.group(2))
  else:
    match = re.match(r"=*\s(\d*)\spassed.*", res_line)
    if match:
      passed = int(match.group(1))
      failed = 0
    else:
      match = re.match(r"=*\s(\d*)\sfailed.*", res_line)
      if match:
        passed = 0
        failed = int(match.group(1))
      else:
        logging.error("Failed to parse score line: " + res_line)
        # TODO: throw exception

  percent = float(passed) / (passed+failed)
  return (passed, failed, percent)

def run_student_tests(target_folder, total_points, timeout):
  logging.debug("Running student tests in: " +target_folder)
  cur_directory = os.getcwd()

  logging.debug("Changing directory ... ")
  os.chdir(target_folder)
  score = (0, 0, 0) # passed, failed, percent

  logging.debug("Capturing stdout")
  from cStringIO import StringIO
  old_stdout = sys.stdout
  sys.stdout = mystdout = StringIO()

  import pytest
  pytest.main(['--timeout=' + str(timeout)])
  logging.debug("Restoring stdout")

  sys.stdout = old_stdout
  out = mystdout.getvalue()

  # print out
  res_line = out.splitlines()[-1]
  score = get_score_from_result_line(res_line, total_points)

  logging.debug("Restoring working directory ...")

  logging.debug("Read test line [" + res_line.strip("=") + "]")
  logging.debug("Calculated score: " + str(score))
  os.chdir(cur_directory)

  return (score, out)

def grade_student_assignment(tag, student_id, incoming_assignments_folder, global_identifier, a_config):
  from shutil import copy

  logging.info("=======================================")
  logging.info("Grading assignment for stduent: " + student_id)

  # copy all needed files to the target folder from source folder
  target_folder = os.path.join(global_identifier, "test-" + tag, student_id)
  if not os.path.exists(target_folder):
    logging.debug("Creating directory: " + target_folder)
    os.makedirs(target_folder)
  init_file = os.path.join(target_folder, "__init__.py")
  touch(init_file)

  instructor_folder = os.path.join(global_identifier, tag)
  logging.debug("Moving files from " + instructor_folder  + " to " + target_folder)

  files_to_move = []
  files_to_move.extend(a_config['instructor_tests'])
  files_to_move.extend(a_config['student_tests'])
  files_to_move.extend(a_config['other_files'])

  logging.debug("Files to move: " + str(files_to_move))

  for f in files_to_move:
    src_file = os.path.join(instructor_folder, f)
    copy(src_file, target_folder)

  # get student files
  modifiable_files = a_config['modifiable_files']
  src_folder = os.path.join(incoming_assignments_folder, student_id, tag)
  logging.debug("Getting student files from: " + src_folder)
  for f in modifiable_files:
    try:
      copy(os.path.join(src_folder, f), target_folder)
    except IOError:
      logging.warning("Student file not found: " + f + " for: " + student_id)
      # TODO: mark as 0 ?!
      return

  # run tests now
  score, outlog = run_student_tests(target_folder, a_config['total_points'], a_config['timeout'])
  write_student_log(src_folder, outlog)

  return score

def grade_assignment(tag):
  set_logging_params(tag)
  logging.debug("Grading assignment: " + tag)

  target_folder = os.path.join(global_identifier, "test-" + tag)
  if os.path.exists(target_folder):
    print "Test folder exists: " + target_folder
    print "Delete it? (y/n) ",
    choice = raw_input()
    if choice == 'y':
      from shutil import rmtree
      logging.debug("Removing test folder tree: " + target_folder)
      rmtree(target_folder)
    else:
      print "Test folder exists. Quitting ... "
      sys.exit(0)


  student_ids = get_student_ids(incoming_assignments_folder)

  logging.info("Total number of students: " + str(len(student_ids)))

  a_config = get_assignment_config(tag, global_identifier)

  all_student_res = {}
  for student_id in student_ids:
    score = grade_student_assignment(tag, student_id, incoming_assignments_folder, global_identifier, a_config)
    all_student_res[student_id] = score

  # print all_student_res
  keylist = all_student_res.keys()
  keylist.sort()
  out_filename = "test-results-" + tag + "-" + current_timestamp + ".csv"

  logging.debug(" ")
  logging.debug("Writing csv output for all students: " + out_filename)

  with open(out_filename, 'w') as csvfile:
    writer = csv.writer(csvfile, delimiter=',')
    writer.writerow(['student_id', 'passed', 'failed', 'percentage'])
    for key in keylist:
      score = list(all_student_res[key])
      score.insert(0, key)
      writer.writerow(score)

  logging.debug("Done.")
  print "Done"

if __name__ == '__main__':
  tag = 'a01'
  grade_assignment(tag)
