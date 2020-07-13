import contextlib
import io
import multiprocessing as mp
from autograder.tests import BaseTest
from .printing import StatusMessage

class TestRunner:
    def __init__(self, res_queue, print_val, print_condn):
        """
        A pickle-able object to use for multiprocessing test running.

        Arguments
        ---------
        res_queue (mp.Queue) -- The queue in which to add the result of the 
            test.
        print_val (mp.Value) -- The value of the thread that has the okay to 
            print.
        print_condn (mp.Condition) -- The condition on which the process should
            wait to print
        """
        self.queue = res_queue
        self.print_val = print_val
        self.print_condn = print_condn


    def __call__(self, index, test):
        # Run test
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            passed = test.run()
        out = f.getvalue()

        # Queue result
        self.queue.put(passed)

        # Print result
        with self.print_condn:
            while not self.print_val.value == index:
                self.print_condn.wait()
        
            print(out, end='')
            self.print_val.value += 1
            self.print_condn.notify_all()


class TestSuite:
    def __init__(self, tests=[], multiprocess=False):
        """
        A collection of tests to be run together. Supports multiprocessing.
        """
        # Initialize the tests
        self.tests = []
        for test in tests:
            self.add_test(test)

        self.multiprocess = multiprocess


    def add_test(self, test):
        """
        Adds test to the internal collection of tests.
        """
        if not isinstance(test, BaseTest):
            raise ValueError(
                f"Can't write a {type(test)} object to the TestRunner (expected"
                f" a test object)."
            )

        self.tests.append(test)


    @staticmethod
    def _close_suite(num_tests, num_passed):
        status = 'success' if num_tests == num_passed else 'warning'

        print()
        print(StatusMessage(
            f"{num_passed} / {num_tests} tests passed.",
            status
        ))


    def _run_mp(self):
        """
        Runs the tests in a multiprocessing pool.
        """
        # Twice as many workers because why not?
        num_workers = mp.cpu_count() * 2
        manager = mp.Manager()
        passed_q = manager.Queue()

        # Two resources for printing: the process that can print and the condn
        print_val = manager.Value(int, 0)
        print_condn = manager.Condition()

        # Put the tests into a pool.
        with mp.Pool(num_workers) as p:
            p.starmap(
                TestRunner(passed_q, print_val, print_condn), 
                enumerate(self.tests)
            )

        # Calculate the number that passed
        num_passed = 0
        while not passed_q.empty():
            passed = passed_q.get()
            if passed:
                num_passed += 1

        self._close_suite(len(self.tests), num_passed)


    def _run_normal(self):
        """
        Runs all of the tests in order.
        """
        num_passed, num_tests = 0, len(self.tests)

        for test in self.tests:
            if test.run():
                # Test passed
                num_passed += 1

        self._close_suite(num_tests, num_passed)


    def run(self):
        if self.multiprocess:
            self._run_mp()

        else:
            self._run_normal()