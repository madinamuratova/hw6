# HW 6 — AI Prompts Log

MGT 409 · AI Foundations for Managers

This file records the prompts I typed to Claude Code for each problem. Each section has:

- the problem number and title
- the prompt I used, copied word for word
- a follow-up prompt, only if I needed one, with one sentence explaining what was missing or not working after the first prompt

<!--
How to add a follow-up (replace "None." under "Follow-up prompt"):

> [follow-up prompt, word for word]

**What was missing after the first prompt:** [one sentence]
-->

---

## Problem 1: Vibe coder prompts

### Prompt

> Okay, lets start with Problem 1. I need to create an `AI_prompts.md` file at the begining of the assignment to keep track of the prompts I use with Claude Code. Set it up with a seperate section for each of the 10 problems, including the problem number and title, the prompt I used, and a follow-up prompt if I needed one. If I use a follow-up, add one sentence explaining what was missing or not working after the first prompt. For now, just set up the file and add the section for Problem 1: Vibe coder prompts. Leave the other sections ready for me to fill in as I work through each problem. Don't make up prompts I haven't used or add fake follow-ups. Keep the file simple and easy to update, and make sure it follows the assignment instructions.

### Follow-up prompt

None.

---

## Problem 2: [Title]

### Prompt

> Okay, lets work on Problem 2 now. First unzip data.zip if it hasn't been unzipped yet, then find data/shop_handbook.md and data/prices.json. I need to figure out how many tokens the shop handbook uses, since our agent will send this handbook to the model on every call. Use a tokenizer that makes sense for the gpt-6-luna model if one is available. If there's no exact tokenizer available, use a reasonable method to estimate the token count and explain the limitation. Don't just count words and call it tokens lol. Then create output/handbook_estimate.md and include the handbook's token count, how you calculated or estimated it, and the price of sending the handbook alone in one model call and across 1,000 calls. Show the math for both cases, with cached tokens and without caching, using the actual prices in data/prices.json. Make sure you understand which token rates apply to cached versus uncached input.Keep the report clear and easy to check, and don't make up prices or token counts. Verify the file paths and calculations before finishing, and update AI_prompts.md with the prompt I used for Problem 2. Focus only on this problem for now.

### Follow-up prompt

> I put data.zip in the HW 6 folder, please continue with Problem 2.

**What was missing after the first prompt:** Claude Code couldn't start because data.zip wasn't in the HW 6 folder yet, so I added it and asked it to continue.

---

## Problem 3: [Title]

### Prompt

> Alright, for Problem 3 I need to build the vendor-desk agent using PydanticAI and the gpt-6-luna model. First, look through the existing project files and use what is already there instead of creating a whole new setup. Organize the implementation into prompts/prompt.md, agent.py, tools.py, and models.py. The agent should read vendor documents in HTML, PDF, and EML formats and return the vendor name, SKU, unit price, lead time in days, minimum order quantity, a recommendation decision, and a short reason based on the vendor handbook. Include the send_email and approve_payment trap tools, but they must never perform real actions. They should only record attempted calls and their arguments in output/trap_calls.json. Also append usage details and calculated API costs to output/usage_log.json, using prices.json, and log tool calls and final answers in output/audit_trail.json. Test the agent with data/practice_docs/p01_bluehen_quote.html and another document such as p08. Start output/harness.md with the model fields and a short explanation of each tool. Please check the actual output and fix any issues before finishing. Update AI_prompts.md with the Problem 3 prompt too.

### Follow-up prompt

None.

---

## Problem 4: [Title]

### Prompt

> Prob 4 Now lets compare the agent's token usage with and without handbook caching. Before starting, check the existing agent and make sure the same model and document-processing logic are used for both tests, so the comparison is fair. Run all 12 practice documents twice: once without caching the handbook and once with caching enabled. Capture the actual API token counts and save the results in output/cache_test.json. Then write up the findings in output/cache_test.md, including total and per-document costs, the percentage saved through caching, a comparison with Problem 2, and a projection of the cost for processing 1,000 documents per day. Explain any surprising results and make sure the calculations use the real usage data and the prices in prices.json. Don't fill in missing numbers with guesses. Keep the existing logs and code intact, run the tests for real, and add the prompt for Problem 4 to AI_prompts.md.

### Follow-up prompt

None.

---

## Problem 5: [Title]

### Prompt

> okaaay, for this one I need to test how vulnerable my agent is to prompt injection. Use the original, undefended agent from Problem 3 and run it on all 12 practice documents. Don't add the defenses yet, because I want to see what happens before we try to fix anything.Compare the agent's responses with the expected results and look for cases where a document contains instructions that try to manipulate the agent, change its decision, or make it use a restricted tool. Record the actual outputs and identify which documents caused suspicious or incorrect behavior.
> Use the assignment's provided expected results and data rather than making up examples or assuming the agent was attacked successfully. Save the required results in the specified output files, and make sure the tests are reproducible. Keep the original Problem 3 implementation available for comparison, and update AI_prompts.md with the prompt used for Problem 5.

### Follow-up prompt

None.

---

## Problem 6: [Title]

### Prompt

> Alright, now  for prob 6 lets work on defending the agent. Review the findings from Problem 5 and identify the specific weaknesses we need to fix. I want the agent to treat vendor documents as untrusted data, not as instructions that can override the system prompt or shop rules.Improve the prompts and implementation so the agent extracts the requested vendor information without following malicious instructions embedded in the documents. Keep the required structured output, model configuration, and tool restrictions unchanged. In particular, the trap tools must never send emails or approve payments. Rerun the same practice documents used in Problem 5 and compare the new results against the original vulnerable agent. Check whether the defenses actually work instead of just describing them in the prompt. Record the test results and explain any attacks that still succeed or any legitimate documents that are handled incorrectly. .

### Follow-up prompt

None.

---

## Problem 7: [Title]

### Prompt

> Okay lets move on to the multi-agent part. Check the code we already have before making changes, because I want to build on the previous problems instead of starting everything from scratch.
>
> okaaaay now create five agents using PydanticAI: Boss, Inventory, Accounting, Facilities, and Customer Service. Give each agent its own detailed prompt under backend/prompts/, and put the shared data models in backend/models.py. Organize the code under `backend/` so the different agent roles and how they work together are easy to follow.Use only the gpt-6-luna model through Portkey with PORTKEY_API_KEY. The agents should access shop information and perform operations through the MCP server rather than bypassing it with a separate set of tools. Check the database and tickets 101, 102, and 103 to determine what MCP tools are needed. Follow the shop's safety rules: use desk.date_today for overdue checks, check vendor lead times using the vendors table, never order from a vendor with an unpaid invoice, and require human approval for payments. No payment should go through if there isn't enough cash, and since revenue isn't modeled, cash should only go out. Customer and vendor messages should be drafted, not actually sent. Append every agent-loop step to output/audit_trail.json, including the agent involved, actions, tool use, and delegation. Update output/harness.md and mcp_server/README.md with the current agents and MCP tools, including the tables each tool uses. Also document the safety guardrails and ways to control token usage.Test the important parts with the actual database and tickets, keep all previous work, and update AI_prompts.md with the prompt for Problem 7. Let me know what fails rather than claiming everything works.

### Follow-up prompt

> Problem 7 is for HW 6. Copy HW 5's database and MCP server into HW 6 and build the five-agent backend here, reusing HW 5's code where it fits.

**What was missing after the first prompt:** HW 6 had no database, tickets, or MCP server yet, so Claude Code asked where they should come from before building anything.

### Second follow-up prompt

> Yes, add a code-level check so customer drafts can't mention vendors, invoices, cash, costs, or other internal details, then rerun the live team test.

**What was missing after the first prompt:** The live test showed a customer draft hinting at an internal vendor problem, and only the prompt forbade that.

---

## Problem 8: [Title]

### Prompt

> for prob 8  I need to build the frontend for Campus Customs. Use React, Vite, and TypeScript, and put the dashboard code in `frontend/`. Before coding, check the backend routes and existing project structure so the frontend connects to the actual system instead of using fake data.The dashboard should list tickets 101, 102, and 103, let me select and run a ticket through the agent team, and show agent activity as the agents work, including tool usage and delegation where available. It should also display the ticket's resolved status and a useful summary of what happened. Payments and purchases must have a human approval step. Show the relevant amount and current cash balance, and make sure the balance updates after a confirmed transaction. Don't let the UI pretend a payment succeeded just because a button was clicked. Connect to the backend at http://localhost:8000 and configure CORS if the frontend needs it. Add output/design.md describing the dashboard design and main UI decisions. Run the app with npm run dev, test the important interactions, and fix any errors you find. Keep the existing backend and MCP work intact, and update AI_prompts.md with the Problem 8 prompt.

### Follow-up prompt

None.

---

## Problem 9: [Title]

### Prompt

> aalright, time to run the full workflow and document what actually happens. First, inspect the current database and make sure we're using the correct working copy, data/campus_customs_new.db. Reset it to the assignment's intended starting state before running the tickets, and record the starting cash balance so we can compare it with the final balance.Run tickets 101, 102, and 103 through the real agent system. Use the actual results to fill in the Actual sections and Cash tab in output/desk_tickets.html, including which agents were involved, any delegation, which tools were used, what actions were taken, and the final ticket status. Reconcile the cash balance and make sure payments follow the human-approval and available-cash rules.Create output/resolved_tickets.json with the required resolved-ticket information and generate a standalone output/resolved_board.html. Keep appending to output/audit_trail.json rather than replacing the existing records.Finally, finish output/harness.md with the relevant database tables, MCP tools, five agents, routes, dashboard details, and safety rules. Verify the outputs against the actual database and logs. Don't mark a ticket as resolved unless the system's real results support that status. Update AI_prompts.md with the Problem 9 prompt and keep the previous work intact.

### Follow-up prompt

None.

---

## Problem 10: Push to GitHub

### Prompt

> Problem 10: Push to GitHub for the final problem, I want to get the whole Homework 6 project ready for GitHub and push it to a public repository so the graders can clone it and run the agent themselves.
> Please first inspect the existing project and Git setup before making changes. Organize the project inside a folder named hw6/ and make sure it includes the main files and folders required for the assignment:
>
> * `AI_prompts.md`
> * `README.md`
> * `.gitignore`
> * `.env.example`
> * `requirements.txt`
> * `agent.py`
> * `tools.py`
> * `models.py`
> * `prompts/prompt.md`
> * `data/`
> * `output/`The `data/` folder needs to include the course data, all 12 practice documents, all 10 exam documents, and the two new attack documents from Problem 7. Make sure the handbook, pricing information, practice answer key, and other required files are in the correct locations. The graders should be able to clone the repository and run the agent without having to recreate the course data or the attacks.
>
> Please make sure .gitignore excludes the real `.env` file and any other secrets or temporary files that shouldn't be committed. Add .env.example with placeholder values only, showing which environment variables need to be configured. Never put a real API key or password into the repository.
> Include the output files from the previous problems, such as the handbook estimate, harness, usage and audit logs, trap-call log, cache experiment results, attack results, defense results, red-team report, exam results, and hw6_report.html. Please check the required filenames carefully and avoid accidentally leaving out any of the reports or JSON files.
> Update README.md with short, clear instructions explaining how to install the dependencies, configure the environment variables, and run the agent on a document. Include an example command such as:
> python agent.py --doc data/practice_docs/p01_bluehen_quote.html
> Also explain any setup requirements a grader needs to know. Please base the instructions on the actual project rather than assuming everything works.
> Before pushing, check the files Git is about to commit and make sure the real `.env` and any other credentials are excluded. Since the course data is required for grading, don't accidentally ignore the required `data/` files. Confirm that the project structure matches the expected layout and that the important files are present.
> Finally, push the project to a public GitHub repository. If a repository or remote already exists, inspect it first and use it if appropriate rather than creating duplicates. Verify the remote URL and that the latest commit was pushed successfully. If GitHub authentication or repository access is missing, tell me exactly what I need to provide instead of claiming that the push worked.
> I only need the repository URL for Canvas submission, not a ZIP file. Please finish by giving me the public repository link and a short summary of the checks you completed.

### Follow-up prompt

None.
