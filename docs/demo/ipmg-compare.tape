# Change detection demo for the README, rendered with VHS
# (https://github.com/charmbracelet/vhs). From the repository root:
#
#   vhs docs/demo/ipmg-compare.tape
#
# Everything runs for real against docs/demo/targets.txt (public DNS resolvers
# plus TEST-NET addresses that never answer) with a throwaway history database.
# See docs/record-demo.md.

Output docs/assets/ipmg-compare.gif

Set Shell "bash"
Set FontSize 16
Set Width 1280
Set Height 760
Set Padding 24
Set Theme "Monokai Vivid"
Set TypingSpeed 35ms
Set WaitTimeout 60s
Set WaitPattern /^\$ ?$/

# Use the repository's .venv, work in a scratch directory, keep the prompt short.
Hide
Type `export PATH="$PWD/.venv/bin:$PATH" PS1='$ '; cd "$(mktemp -d)" && cp "$OLDPWD/docs/demo/targets.txt" . && clear`
Enter
Wait
Show

Type "ipmg --input targets.txt --db history.db --formats md"
Sleep 400ms
Enter
Wait
Sleep 2s

Type "echo 192.0.2.30 >> targets.txt    # a device joins the network"
Sleep 400ms
Enter
Wait
Sleep 1s

Type "ipmg --input targets.txt --db history.db --formats md --compare"
Sleep 400ms
Enter
Wait
Sleep 6s
