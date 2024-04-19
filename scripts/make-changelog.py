import os

changelog_dir = 'changelog.d'

def main():
    lines = []
    for fn in os.listdir(changelog_dir):
        p = os.path.join(changelog_dir, fn)
        with open(p, 'r') as f:
            s = f.read()
        line = f'- {s}'
        lines.append(line)
    head = '# Changelog\n\n'
    cl = head + '\n'.join(lines)
    print(cl)

if __name__ == '__main__':
    main()
