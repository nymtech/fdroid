package dir

import (
	"os"
	"path/filepath"
)

func GetUniqueDirectories(paths []string) []string {
	seenDirs := make(map[string]bool)

	for _, path := range paths {
		info, err := os.Stat(path)
		if err == nil && info.IsDir() {
			seenDirs[filepath.Clean(path)] = true
			continue
		}

		dir := filepath.Dir(path)
		seenDirs[dir] = true
	}

	uniqueDirs := make([]string, 0, len(seenDirs))
	for dir := range seenDirs {
		uniqueDirs = append(uniqueDirs, dir)
	}

	return uniqueDirs
}
