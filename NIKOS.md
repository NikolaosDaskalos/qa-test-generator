# Repository configuration 
Before create a repository you need to provide a Fine-grained PAT token from GitHub follow this steps: 
1. Log in to your GitHub account
2. Visit GitHub access token screen https://github.com/settings/personal-access-tokens?utm_source=chatgpt.com
3. In the left menu go to personal access tokens -> fine grained tokens -> click generate new token
4. Under **Repository access** section choose the specific repository wou want to give it access or more repositories
5. Under **Permissions** section click **Add permissions** button and choose:
   - Contents  
   - Pull Requests
6. Change both to **Access: read and write**
7. Click generate token



Configure:

* Resource owner: your account or organization
* Repository access: Only select repositories
* Permissions:
    * Contents: Read and Write (required for clone/push)
    * Pull requests: Read and Write (if creating PRs)
    * Workflows: Read and Write (only if modifying workflow files) 

