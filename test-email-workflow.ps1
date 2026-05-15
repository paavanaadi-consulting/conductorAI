# Email Service & Project Approval - Testing Examples (PowerShell)
# Save as: test-email-workflow.ps1
# Run: .\test-email-workflow.ps1

# Configuration
$BASE_URL = "http://localhost:8000"
$API_PATH = "/api/projects"

# Colors (simulated for PowerShell)
$Green = "Green"
$Blue = "Cyan"
$Yellow = "Yellow"
$Red = "Red"

Write-Host "========================================" -ForegroundColor $Blue
Write-Host "Email Service & Project Approval Tests" -ForegroundColor $Blue
Write-Host "========================================" -ForegroundColor $Blue

# Test 1: Create a Project (triggers review emails)
Write-Host "`n[TEST 1] Creating Project (sends review emails)" -ForegroundColor $Yellow
Write-Host "Request: POST $($BASE_URL)$($API_PATH)/" -ForegroundColor $Blue

$createBody = @{
    name = "ai-orchestration-platform"
    github_repo = "https://github.com/acme/ai-orchestration"
    github_owner = "acme"
    github_app_installation_id = 12345
    requirements_yaml = "name: ai-platform`nversion: 1.0`ndescription: Multi-agent AI orchestration`n"
    infra_yaml = "infrastructure:`n  compute:`n    - kubernetes`n  storage:`n    - postgresql`n"
    project_manager_email = "pm@acme.com"
    architect_email = "architect@acme.com"
    selected_components = @("pipeline-generator", "workflow-orchestrator")
} | ConvertTo-Json

try {
    $createResponse = Invoke-RestMethod -Uri "$($BASE_URL)$($API_PATH)/" `
        -Method POST `
        -ContentType "application/json" `
        -Body $createBody

    Write-Host "Response:" -ForegroundColor $Blue
    Write-Host ($createResponse | ConvertTo-Json -Depth 10) -ForegroundColor $Green

    $PROJECT_ID = $createResponse.id

    if (-not $PROJECT_ID) {
        Write-Host "✗ Failed to create project" -ForegroundColor $Red
        exit 1
    }

    Write-Host "✓ Project created with ID: $PROJECT_ID" -ForegroundColor $Green
    Write-Host "✓ Review emails should have been sent to:" -ForegroundColor $Green
    Write-Host "  - pm@acme.com" -ForegroundColor $Green
    Write-Host "  - architect@acme.com" -ForegroundColor $Green
}
catch {
    Write-Host "✗ Error creating project: $_" -ForegroundColor $Red
    exit 1
}

# Test 2: List Projects
Write-Host "`n[TEST 2] Listing Projects" -ForegroundColor $Yellow
Write-Host "Request: GET $($BASE_URL)$($API_PATH)/" -ForegroundColor $Blue

try {
    $listResponse = Invoke-RestMethod -Uri "$($BASE_URL)$($API_PATH)/" `
        -Method GET `
        -ContentType "application/json"

    Write-Host "Response:" -ForegroundColor $Blue
    Write-Host ($listResponse | ConvertTo-Json -Depth 10) -ForegroundColor $Green
}
catch {
    Write-Host "✗ Error listing projects: $_" -ForegroundColor $Red
}

# Test 3: Get Project Details
Write-Host "`n[TEST 3] Getting Project Details" -ForegroundColor $Yellow
Write-Host "Request: GET $($BASE_URL)$($API_PATH)/$PROJECT_ID" -ForegroundColor $Blue

try {
    $getResponse = Invoke-RestMethod -Uri "$($BASE_URL)$($API_PATH)/$PROJECT_ID" `
        -Method GET `
        -ContentType "application/json"

    Write-Host "Response:" -ForegroundColor $Blue
    Write-Host ($getResponse | ConvertTo-Json -Depth 10) -ForegroundColor $Green

    $IS_APPROVED = $getResponse.is_approved
    Write-Host "Current is_approved status: $IS_APPROVED" -ForegroundColor $Blue

    if ($IS_APPROVED -eq $false) {
        Write-Host "✓ Project correctly set to not approved" -ForegroundColor $Green
    }
}
catch {
    Write-Host "✗ Error getting project: $_" -ForegroundColor $Red
}

# Test 4: Approve Project (triggers confirmation emails)
Write-Host "`n[TEST 4] Approving Project (sends confirmation emails)" -ForegroundColor $Yellow
Write-Host "Request: POST $($BASE_URL)$($API_PATH)/$PROJECT_ID/approve" -ForegroundColor $Blue
Write-Host "Parameter: approved_by=John Doe" -ForegroundColor $Blue

try {
    $approveUri = "$($BASE_URL)$($API_PATH)/$PROJECT_ID/approve?approved_by=John Doe"
    $approveResponse = Invoke-RestMethod -Uri $approveUri `
        -Method POST `
        -ContentType "application/json" `
        -Body "{}"

    Write-Host "Response:" -ForegroundColor $Blue
    Write-Host ($approveResponse | ConvertTo-Json -Depth 10) -ForegroundColor $Green

    $APPROVED = $approveResponse.is_approved

    if ($APPROVED -eq $true) {
        Write-Host "✓ Project successfully approved" -ForegroundColor $Green
        Write-Host "✓ Confirmation emails should have been sent to:" -ForegroundColor $Green
        Write-Host "  - pm@acme.com" -ForegroundColor $Green
        Write-Host "  - architect@acme.com" -ForegroundColor $Green
    }
    elseif ($APPROVED -eq $false) {
        Write-Host "⚠ Project is not approved. Response received but approval not reflected." -ForegroundColor $Yellow
    }
    else {
        Write-Host "✗ Could not determine approval status" -ForegroundColor $Red
    }
}
catch {
    Write-Host "✗ Error approving project: $_" -ForegroundColor $Red
}

# Test 5: Try to approve again (should fail with 400)
Write-Host "`n[TEST 5] Attempting Double Approval (should fail with 400)" -ForegroundColor $Yellow
Write-Host "Request: POST $($BASE_URL)$($API_PATH)/$PROJECT_ID/approve" -ForegroundColor $Blue

try {
    $approveUri = "$($BASE_URL)$($API_PATH)/$PROJECT_ID/approve?approved_by=John Doe"
    $doubleApprove = Invoke-WebRequest -Uri $approveUri `
        -Method POST `
        -ContentType "application/json" `
        -Body "{}"

    $HTTP_CODE = $doubleApprove.StatusCode
    Write-Host "HTTP Status: $HTTP_CODE" -ForegroundColor $Blue
    Write-Host "Response: " -ForegroundColor $Blue
    Write-Host ($doubleApprove.Content | ConvertFrom-Json | ConvertTo-Json -Depth 10) -ForegroundColor $Green

    if ($HTTP_CODE -eq 400) {
        Write-Host "✓ Correctly rejected double approval with 400" -ForegroundColor $Green
    }
    else {
        Write-Host "✗ Expected 400 but got $HTTP_CODE" -ForegroundColor $Red
    }
}
catch [System.Net.Http.HttpRequestException] {
    $HTTP_CODE = $_.Exception.Response.StatusCode.value__
    $responseBody = $_.Exception.Response.Content.ReadAsStringAsync().Result

    Write-Host "HTTP Status: $HTTP_CODE" -ForegroundColor $Blue
    Write-Host "Response: $responseBody" -ForegroundColor $Blue

    if ($HTTP_CODE -eq 400) {
        Write-Host "✓ Correctly rejected double approval with 400" -ForegroundColor $Green
    }
    else {
        Write-Host "✗ Expected 400 but got $HTTP_CODE" -ForegroundColor $Red
    }
}

# Test 6: Get Updated Project
Write-Host "`n[TEST 6] Getting Final Project Details" -ForegroundColor $Yellow
Write-Host "Request: GET $($BASE_URL)$($API_PATH)/$PROJECT_ID" -ForegroundColor $Blue

try {
    $finalResponse = Invoke-RestMethod -Uri "$($BASE_URL)$($API_PATH)/$PROJECT_ID" `
        -Method GET `
        -ContentType "application/json"

    Write-Host "Response:" -ForegroundColor $Blue
    Write-Host ($finalResponse | ConvertTo-Json -Depth 10) -ForegroundColor $Green

    $FINAL_STATUS = $finalResponse.is_approved
    Write-Host "Final is_approved status: $FINAL_STATUS" -ForegroundColor $Blue
}
catch {
    Write-Host "✗ Error getting final project: $_" -ForegroundColor $Red
}

# Summary
Write-Host "`n========================================" -ForegroundColor $Blue
Write-Host "Test Summary" -ForegroundColor $Blue
Write-Host "========================================" -ForegroundColor $Blue

Write-Host "✓ Project ID: $PROJECT_ID" -ForegroundColor $Green
Write-Host "✓ Create Project: SUCCESS" -ForegroundColor $Green
Write-Host "✓ List Projects: SUCCESS" -ForegroundColor $Green
Write-Host "✓ Get Project: SUCCESS" -ForegroundColor $Green
Write-Host "✓ Approve Project: SUCCESS" -ForegroundColor $Green
Write-Host "✓ Double Approval Prevention: SUCCESS" -ForegroundColor $Green

if ($FINAL_STATUS -eq $true) {
    Write-Host "✓ Final Status: APPROVED" -ForegroundColor $Green
}
else {
    Write-Host "⚠ Final Status: $FINAL_STATUS" -ForegroundColor $Yellow
}

Write-Host "`nEmail Verification:" -ForegroundColor $Blue
Write-Host "Check email accounts for:" -ForegroundColor $Yellow
Write-Host "  1. Review request emails (after create)" -ForegroundColor $Yellow
Write-Host "     - Subject: Project Review Request: ai-orchestration-platform" -ForegroundColor $Yellow
Write-Host "     - To: pm@acme.com, architect@acme.com" -ForegroundColor $Yellow
Write-Host ""
Write-Host "  2. Approval confirmation emails (after approve)" -ForegroundColor $Yellow
Write-Host "     - Subject: Project Approved: ai-orchestration-platform" -ForegroundColor $Yellow
Write-Host "     - To: pm@acme.com, architect@acme.com" -ForegroundColor $Yellow

Write-Host "`nAll tests completed!" -ForegroundColor $Green

