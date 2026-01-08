# Fuzz Testing

Fuzz testing is:

> An automated software testing technique that involves providing invalid, unexpected, or random data as inputs to a program.

We use coverage guided fuzz testing to automatically discover bugs in python-multipart.

This `fuzz/` directory contains the configuration and the fuzz tests for python-multipart.
To generate and run fuzz tests, we use the [Atheris](https://github.com/google/atheris) library.

## Running a fuzzer

This directory contains fuzzers like for example `fuzz_form.py`. You can run it with:

Run fuzz target:
```sh
$ python fuzz/fuzz_form.py
```

You should see output that looks something like this:

```
#2      INITED cov: 32 ft: 32 corp: 1/1b exec/s: 0 rss: 49Mb
#3      NEW    cov: 33 ft: 33 corp: 2/2b lim: 4 exec/s: 0 rss: 49Mb L: 1/1 MS: 1 ChangeByte-
#4      NEW    cov: 97 ft: 97 corp: 3/4b lim: 4 exec/s: 0 rss: 49Mb L: 2/2 MS: 1 InsertByte-
#11     NEW    cov: 116 ft: 119 corp: 4/5b lim: 4 exec/s: 0 rss: 49Mb L: 1/2 MS: 2 ChangeBinInt-EraseBytes-
#30     NEW    cov: 131 ft: 134 corp: 5/8b lim: 4 exec/s: 0 rss: 49Mb L: 3/3 MS: 4 ChangeByte-ChangeBit-InsertByte-CopyPart-
#31     NEW    cov: 135 ft: 138 corp: 6/11b lim: 4 exec/s: 0 rss: 49Mb L: 3/3 MS: 1 CrossOver-
#39     NEW    cov: 135 ft: 142 corp: 7/15b lim: 4 exec/s: 0 rss: 49Mb L: 4/4 MS: 3 ChangeBit-CrossOver-CopyPart-
```

It will continue to generate random inputs forever, until it finds a
bug or is terminated. The testcases for bugs it finds can be seen in
the form of `crash-*` or `timeout-*` at the place from where command is run.
You can rerun the fuzzer on a single input by passing it on the
command line `python fuzz/fuzz_form.py /path/to/testcase`.
