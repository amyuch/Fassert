import re


def _legacy_get_signal(lines, prefix):
    """Parse the pre-0.5x Yosys log format.

    Older Yosys builds printed the optimized wires as bare lines after the
    OPT_EXPR / OPT_CLEAN passes, e.g. ``\\RTL.foo``.  Keep this path so the
    script still works with the Yosys versions the original flow used.
    """
    signals = []
    found_expr_key_line = False
    found_clean_key_line = False
    lines_after_expr_key = 0

    for line in lines:
        line = line.rstrip()

        if not found_expr_key_line and "Executing OPT_EXPR pass (perform const folding)." in line:
            found_expr_key_line = True
            continue

        if found_expr_key_line:
            lines_after_expr_key += 1
            if lines_after_expr_key <= 2:
                continue

            if line.startswith(f'\\{prefix}'):
                signals.append(line)

            if line.strip() == "":
                found_expr_key_line = False
                lines_after_expr_key = 0

        if not found_clean_key_line and "Executing OPT_CLEAN pass (remove unused cells and wires)." in line:
            found_clean_key_line = True
            continue

        if found_clean_key_line:
            # The optimized part lives in the submodule, so look for the
            # instance prefix (normally "\RTL.").
            if line.startswith(f'\\{prefix}.'):
                signals.append(line)

            if line.strip() == "":
                found_clean_key_line = False

    return signals


def _modern_get_signal(text, prefix):
    """Parse the Yosys >= 0.5x debug log format.

    Newer Yosys builds do not print bare ``\\RTL.<wire>`` lines during
    opt_expr/opt_clean.  With debug logging enabled (``yosys -g``) they emit
    messages such as::

        Replacing $eq cell `$flatten\\RTL.foo' ... with constant driver ...
        removing unused non-port wire $flatten\\RTL.bar.

    so collect every ``\\<prefix>.<wire>`` token that appears in the log.
    """
    pattern = re.compile(r'\\' + re.escape(prefix) + r'\.[A-Za-z_][A-Za-z0-9_.\[\]$]*')
    seen = set()
    for match in pattern.finditer(text):
        name = match.group(0).rstrip('.')
        if name:
            seen.add(name)
    return sorted(seen)


def get_signal(input_filename, output_filename, prefix):
    try:
        with open(input_filename, 'r') as infile:
            lines = infile.readlines()

        signals = _legacy_get_signal(lines, prefix)
        if not signals:
            signals = _modern_get_signal("".join(lines), prefix)

        with open(output_filename, 'w') as outfile:
            for signal in signals:
                outfile.write(signal + '\n')

        print(f"Processing complete. Results written to {output_filename}")

    except FileNotFoundError:
        print(f"Error: The file {input_filename} was not found.")
    except Exception as e:
        print(f"An error occurred: {e}")
