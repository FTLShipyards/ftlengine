import difflib

try:
    import pylev
except ImportError:
    pylev = None


if pylev:
    def spell_correct(input, choices, threshold=1.0):
        """
        Find a possible spelling correction for a given input.
        """
        # Try to find corrections using pylev
        guesses = sorted((pylev.levenshtein(c, input), c) for c in choices)
        if not guesses:
            return None
        distance, suggestion = next(iter(guesses))
        # Score the error distance based on word length
        length = max(len(suggestion), len(input))
        score = distance ** 2 / length
        if score <= threshold:
            return suggestion
else:
    def spell_correct(input, choices, threshold=0.6):
        """
        Find a possible spelling correction for a given input.
        """
        guesses = difflib.get_close_matches(input, choices, 1, cutoff=threshold)
        return next(iter(guesses), None)
