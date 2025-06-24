#!/bin/bash

cd metascoop
echo "::group::Building metascoop executable"
go build -o metascoop
echo "::endgroup::"

./metascoop -ap=../apps.yaml -rd=../fdroid/repo -pat="$GH_ACCESS_TOKEN" $1
EXIT_CODE=$?
cd ..

echo "Scoop had an exit code of $EXIT_CODE"

set -e

if [ $EXIT_CODE -eq 2 ]; then
    echo "No significant changes"
    exit 0
elif [ $EXIT_CODE -eq 0 ]; then
    echo "Commit and push changes"

    git add .
    git commit -m "Automated update"
    git push
else 
    echo "Unexpected error: $EXIT_CODE"
    exit $EXIT_CODE
fi
