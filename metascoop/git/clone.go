package git

import (
	"log"
	"os"
	"os/exec"
)

func CloneRepo(gitUrl string) (dirPath string, err error) {
	dirPath, err = os.MkdirTemp("", "git-*")
	if err != nil {
		return dirPath, err
	}

	log.Printf("git clone")
	cloneCmd := exec.Command("git", "clone", "-n", "--depth=1", "--filter=tree:0", gitUrl, dirPath)
	cloneCmd.Stdout = os.Stdout
	cloneCmd.Stderr = os.Stderr
	err = cloneCmd.Run()
	if err != nil {
		return dirPath, err
	}

	log.Printf("git sparse-checkout")
	cloneCmd = exec.Command("git", "-C", dirPath, "sparse-checkout", "set", "--no-cone", "fastlane/")
	cloneCmd.Stdout = os.Stdout
	cloneCmd.Stderr = os.Stderr
	err = cloneCmd.Run()
	if err != nil {
		return dirPath, err
	}

	log.Printf("git checkout")
	cloneCmd = exec.Command("git", "-C", dirPath, "checkout")
	cloneCmd.Stdout = os.Stdout
	cloneCmd.Stderr = os.Stderr
	err = cloneCmd.Run()

	return dirPath, err
}
