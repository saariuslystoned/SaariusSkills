# Antigravity `agentapi` & `LanguageServerService` Complete Catalog (365 RPCs + CLI + Sidecar APIs)

## 1. `agentapi` CLI Commands (`~/.gemini/antigravity/bin/agentapi`)

1. `agentapi new-conversation [--model=<flash_lite|flash|pro|model_id>] [--title=<title>] [--profile=<profile>] <prompt>` — Spawns a top-level sidebar conversation in `ANTIGRAVITY_PROJECT_ID` (defaults to the active project).
2. `agentapi send-message [--title=<title>] <recipient_id> <content>` — Sends a message to any top-level or child conversation UUID.
3. `agentapi get-conversation-metadata <conversation_id>` — Returns workspace URIs, git root, branch, `projectId`, `parentConversationId`, `rootConversationId`, and `sourceMetadata`.

## 2. Built-in Sidecar Runner & HTTP Endpoints

4. `schedule [--once] "<cron_expr>" agentapi new-conversation "<prompt>"` — Built-in cron/timer sidecar runner inside `language_server`.
5. `POST /_sidecar/new-conversation` — Sidecar HTTP bridge (`{message, model, projectId}`).
6. `POST /_sidecar/send-message` — Sidecar HTTP bridge (`{conversationId, message, title, projectId}`).
7. `POST /_sidecar/get-conversation-metadata` — Sidecar HTTP bridge (`{conversationId}`).

## 3. All 365 `LanguageServerService` ConnectRPC Endpoints

Every endpoint below is served over `POST http://$ANTIGRAVITY_LS_ADDRESS/exa.language_server_pb.LanguageServerService/<Method>` with header `x-codeium-csrf-token: $ANTIGRAVITY_CSRF_TOKEN` and `Connect-Protocol-Version: 1`.

| # | Method | Category / Purpose |
| --- | --- | --- |
| 1 | `AcceptTermsOfService` | Onboarding & Auth |
| 2 | `AcknowledgeCascadeCodeEdit` | Code Edit & Diff |
| 3 | `AcknowledgeCodeActionStep` | Code Edit & Diff |
| 4 | `AddEnvironmentToProjectmodelapiinterface` | Projects & Workspaces |
| 5 | `AddToBrowserWhitelist` | Browser Automation |
| 6 | `AddTrackedWorkspace` | Projects & Workspaces |
| 7 | `ApplyUpdate` | App Lifecycle & Updates |
| 8 | `AuthLogout` | Onboarding & Auth |
| 9 | `BrowserValidateCascadeOrCancelOverlay` | Browser Automation |
| 10 | `CallMcpAppTool` | MCP & Plugins |
| 11 | `CancelCascadeInvocation` | Conversation & Cascade Control |
| 12 | `CancelCascadeSteps` | Conversation & Cascade Control |
| 13 | `CaptureConsoleLogs` | Diagnostics & Debugging |
| 14 | `CaptureScreenshot` | Browser & Media |
| 15 | `CheckDevToolsActivePort` | Browser Automation |
| 16 | `CheckoutCommit` | Git, JJ, Fig & Worktrees |
| 17 | `CheckoutWorktree` | Git, JJ, Fig & Worktrees |
| 18 | `CloseTerminal` | Terminals & Execution |
| 19 | `CogCommit` | Git, JJ, Fig & Worktrees |
| 20 | `CogSquash` | Git, JJ, Fig & Worktrees |
| 21 | `CogSync` | Git, JJ, Fig & Worktrees |
| 22 | `CogUpload` | Git, JJ, Fig & Worktrees |
| 23 | `CompleteMcpOAuth` | MCP & Plugins |
| 24 | `ConvertTrajectoryToMarkdown` | Conversation & Cascade Control |
| 25 | `CopyBuiltinWorkflowToWorkspaceinvalid` | Skills, Rules & Workflows |
| 26 | `CreateCitcWorkspace` | Git, JJ, Fig & Worktrees |
| 27 | `CreateCustomizationFile` | Skills, Rules & Workflows |
| 28 | `CreateDebugBundle` | Diagnostics & Debugging |
| 29 | `CreateDirectory` | Filesystem |
| 30 | `CreateMagicProject` | Projects & Workspaces |
| 31 | `CreateProject` | Projects & Workspaces |
| 32 | `CreateScratchProjectFolder` | Projects & Workspaces |
| 33 | `CreateTerminal` | Terminals & Execution |
| 34 | `CreateTrajectoryShare` | Conversation & Cascade Control |
| 35 | `CreateTrigger` | Triggers & Schedules |
| 36 | `CreateWorktree` | Git, JJ, Fig & Worktrees |
| 37 | `DeleteAgentMessage` | Inter-Agent Messaging |
| 38 | `DeleteAllUserData` | User Settings & Privacy |
| 39 | `DeleteCascadeMemory` | Memory & Knowledge |
| 40 | `DeleteCascadeTrajectory` | Conversation & Cascade Control |
| 41 | `DeleteFileOrDirectory` | Filesystem |
| 42 | `DeleteMediaArtifact` | Artifacts & Media |
| 43 | `DeletePlugin` | MCP & Plugins |
| 44 | `DeleteProject` | Projects & Workspaces |
| 45 | `DeleteQueuedUserInputStep` | Conversation & Cascade Control |
| 46 | `DeleteSkill` | Skills, Rules & Workflows |
| 47 | `DeleteTrigger` | Triggers & Schedules |
| 48 | `DeleteWorktree` | Git, JJ, Fig & Worktrees |
| 49 | `DetectBattleModeAutoTrigger` | Battle Mode (Arena) |
| 50 | `DiscardFileChanges` | Git, JJ, Fig & Worktrees |
| 51 | `DisconnectMcpOAuth` | MCP & Plugins |
| 52 | `DisconnectRemotePlugin` | MCP & Plugins |
| 53 | `DownloadBuildWithGooglePlugin` | MCP & Plugins |
| 54 | `DumpFlightRecorder` | Diagnostics & Debugging |
| 55 | `DumpPprof` | Diagnostics & Debugging |
| 56 | `EliminateBattleModeArm` | Battle Mode (Arena) |
| 57 | `EndAudioSession` | Voice & Audio |
| 58 | `EndBattleMode` | Battle Mode (Arena) |
| 59 | `EndNarration` | Voice & Audio |
| 60 | `Exit` | App Lifecycle & Updates |
| 61 | `FetchAdminControls` | Enterprise & Quota |
| 62 | `FetchUserInfo` | User Settings & Privacy |
| 63 | `FigAmend` | Git, JJ, Fig & Worktrees |
| 64 | `FigCommit` | Git, JJ, Fig & Worktrees |
| 65 | `FigSync` | Git, JJ, Fig & Worktrees |
| 66 | `FigUpload` | Git, JJ, Fig & Worktrees |
| 67 | `FocusUserPage` | UI & Focus |
| 68 | `ForceBackgroundResearchRefresh` | Memory & Knowledge |
| 69 | `ForceStopCascadeTree` | Conversation & Cascade Control |
| 70 | `ForkConversation` | Conversation & Cascade Control |
| 71 | `FulfillAgentBrowserRequestSearchMarketplaceCustomizations` | Browser & Marketplace |
| 72 | `GenerateCommitMessage` | Git, JJ, Fig & Worktrees |
| 73 | `GenerateEnvironmentName` | Projects & Workspaces |
| 74 | `GenerateSkillInstallationCL` | Skills, Rules & Workflows |
| 75 | `GetAgentScripts` | Agent Scripts & Profiles |
| 76 | `GetAgentTeamMetadata` | Multi-Agent & Subagents |
| 77 | `GetAllBrowserWhitelistedUrlsproxy` | Browser Automation |
| 78 | `GetAllCascadeTrajectories` | Conversation & Cascade Control |
| 79 | `GetAllCustomAgentConfigs` | Agent Scripts & Profiles |
| 80 | `GetAllPlugins` | MCP & Plugins |
| 81 | `GetAllRules` | Skills, Rules & Workflows |
| 82 | `GetAllSkills` | Skills, Rules & Workflows |
| 83 | `GetAllWorkflows` | Skills, Rules & Workflows |
| 84 | `GetArtifactSnapshots` | Artifacts & Media |
| 85 | `GetAuthStatus` | Onboarding & Auth |
| 86 | `GetAvailableCascadePlugins` | MCP & Plugins |
| 87 | `GetAvailableModels` | Models & Quota |
| 88 | `GetBattleWorktreeDiff` | Battle Mode (Arena) |
| 89 | `GetBrowserOpenConversation` | Browser Automation |
| 90 | `GetBrowserWhitelistFilePath` | Browser Automation |
| 91 | `GetBuildWithGooglePlugins` | MCP & Plugins |
| 92 | `GetCapabilities` | App Lifecycle & Updates |
| 93 | `GetCascadeMemories` | Memory & Knowledge |
| 94 | `GetCascadeModelConfigData` | Models & Quota |
| 95 | `GetCascadeModelConfigs` | Models & Quota |
| 96 | `GetCascadeNuxes` | Onboarding & Auth |
| 97 | `GetCascadePluginById` | MCP & Plugins |
| 98 | `GetCascadeTrajectory` | Conversation & Cascade Control |
| 99 | `GetCascadeTrajectoryExecutorMetadatas` | Conversation & Cascade Control |
| 100 | `GetCascadeTrajectoryGeneratorMetadata` | Conversation & Cascade Control |
| 101 | `GetCascadeTrajectorySteps` | Conversation & Cascade Control |
| 102 | `GetChangelistStatus` | Git, JJ, Fig & Worktrees |
| 103 | `GetChangelog` | App Lifecycle & Updates |
| 104 | `GetChapterTitles` | Conversation & Cascade Control |
| 105 | `GetCodeActionDiff` | Code Edit & Diff |
| 106 | `GetCodeFrequencyForRepo` | Git, JJ, Fig & Worktrees |
| 107 | `GetCodeValidationStates` | Code Edit & Diff |
| 108 | `GetCommandModelConfigs` | Models & Quota |
| 109 | `GetCommitDetails` | Git, JJ, Fig & Worktrees |
| 110 | `GetContribVariants` | Experiments & Flags |
| 111 | `GetConversationMetadata` | Conversation & Cascade Control |
| 112 | `GetCustomizationStates` | Skills, Rules & Workflows |
| 113 | `GetDebugDiagnostics` | Diagnostics & Debugging |
| 114 | `GetDefaultProjectDir` | Projects & Workspaces |
| 115 | `GetGerritChangeStatus` | Git, JJ, Fig & Worktrees |
| 116 | `GetGitHubPullRequests` | Git, JJ, Fig & Worktrees |
| 117 | `GetGoogleChatLinkInfo` | Integrations |
| 118 | `GetGrantedScopes` | Onboarding & Auth |
| 119 | `GetHover` | Code Intelligence |
| 120 | `GetInputCompletion` | Code Intelligence |
| 121 | `GetJJWorktrees` | Git, JJ, Fig & Worktrees |
| 122 | `GetKnowledgeItems` | Memory & Knowledge |
| 123 | `GetLoadCodeAssist` | Onboarding & Auth |
| 124 | `GetLocalUserInfo` | User Settings & Privacy |
| 125 | `GetMarketplaceBundles` | MCP & Plugins |
| 126 | `GetMarketplaceCustomization` | MCP & Plugins |
| 127 | `GetMarketplaceFeatured` | MCP & Plugins |
| 128 | `GetMatchingContextScopeItems` | Search & Context |
| 129 | `GetMcpAppResource` | MCP & Plugins |
| 130 | `GetMcpPrompt` | MCP & Plugins |
| 131 | `GetMcpServerStates` | MCP & Plugins |
| 132 | `GetMcpServerTemplates` | MCP & Plugins |
| 133 | `GetMendelFlags` | Experiments & Flags |
| 134 | `GetModelResponse` | Models & Quota |
| 135 | `GetModelStatuses` | Models & Quota |
| 136 | `GetPatchAndCodeChange` | Code Edit & Diff |
| 137 | `GetPermissionSettings` | Permissions & Security |
| 138 | `GetPlugin` | MCP & Plugins |
| 139 | `GetProfileData` | Agent Scripts & Profiles |
| 140 | `GetRemoteControlInfo` | Remote Control |
| 141 | `GetRepoInfos` | Git, JJ, Fig & Worktrees |
| 142 | `GetRevertPreview` | Conversation & Cascade Control |
| 143 | `GetRevisionArtifact` | Artifacts & Media |
| 144 | `GetServerConfiguration` | App Lifecycle & Updates |
| 145 | `GetSidecarEvents` | Sidecars |
| 146 | `GetSidecarLogs` | Sidecars |
| 147 | `GetSidecars` | Sidecars |
| 148 | `GetSkillMarketplaceLink` | Skills, Rules & Workflows |
| 149 | `GetSlashCommands` | Skills, Rules & Workflows |
| 150 | `GetStandaloneDir` | App Lifecycle & Updates |
| 151 | `GetStaticExperimentStatusinjected` | Experiments & Flags |
| 152 | `GetStatus` | App Lifecycle & Updates |
| 153 | `GetTeamOrganizationalControls` | Enterprise & Quota |
| 154 | `GetTermsOfService` | Onboarding & Auth |
| 155 | `GetTokenBase` | Onboarding & Auth |
| 156 | `GetTrajectoryFileDiffs` | Code Edit & Diff |
| 157 | `GetTrajectoryTurns` | Conversation & Cascade Control |
| 158 | `GetTranscription` | Voice & Audio |
| 159 | `GetTurnDiff` | Code Edit & Diff |
| 160 | `GetUnleashData` | Experiments & Flags |
| 161 | `GetUpdateStatus` | App Lifecycle & Updates |
| 162 | `GetUserAnalyticsSummary` | Telemetry & Analytics |
| 163 | `GetUserDataDeletionStatus` | User Settings & Privacy |
| 164 | `GetUserMemories` | Memory & Knowledge |
| 165 | `GetUserSettings` | User Settings & Privacy |
| 166 | `GetUserStatus` | User Settings & Privacy |
| 167 | `GetUserTrajectory` | Conversation & Cascade Control |
| 168 | `GetUserTrajectoryDebug` | Diagnostics & Debugging |
| 169 | `GetUserTrajectoryDescriptions` | Conversation & Cascade Control |
| 170 | `GetVersionControlFileContent` | Git, JJ, Fig & Worktrees |
| 171 | `GetVersionControlState` | Git, JJ, Fig & Worktrees |
| 172 | `GetVoiceCallDebug` | Voice & Audio |
| 173 | `GetWebDocsOptions` | Search & Context |
| 174 | `GetWorkingDirectories` | Projects & Workspaces |
| 175 | `GetWorkspaceChangelists` | Git, JJ, Fig & Worktrees |
| 176 | `GetWorkspaceEditState` | Code Edit & Diff |
| 177 | `GetWorkspaceGitHubPullRequests` | Git, JJ, Fig & Worktrees |
| 178 | `GetWorkspaceInfos` | Projects & Workspaces |
| 179 | `GetWorktreeDiff` | Git, JJ, Fig & Worktrees |
| 180 | `GitCommit` | Git, JJ, Fig & Worktrees |
| 181 | `GitDiscard` | Git, JJ, Fig & Worktrees |
| 182 | `GitPush` | Git, JJ, Fig & Worktrees |
| 183 | `GitStage` | Git, JJ, Fig & Worktrees |
| 184 | `GitUnstage` | Git, JJ, Fig & Worktrees |
| 185 | `HandleCascadeUserInteraction` | Conversation & Cascade Control |
| 186 | `HandleScreenRecording` | Browser & Media |
| 187 | `HandleStreamingCommand` | Terminals & Execution |
| 188 | `HasAuthToken` | Onboarding & Auth |
| 189 | `Heartbeat` | App Lifecycle & Updates |
| 190 | `ImportFromCursor` | Onboarding & Auth |
| 191 | `ImportProjectFromUrl` | Projects & Workspaces |
| 192 | `InitializeCascadePanelState` | UI & Focus |
| 193 | `InstallCascadePlugin` | MCP & Plugins |
| 194 | `InstallCustomization` | Skills, Rules & Workflows |
| 195 | `JetboxDeleteSummary` | Hub Summary Store (Jetbox) |
| 196 | `JetboxReadAppState` | Hub Summary Store (Jetbox) |
| 197 | `JetboxReadUserConfig` | Hub Summary Store (Jetbox) |
| 198 | `JetboxSubscribeToGcertState` | Hub Summary Store (Jetbox) |
| 199 | `JetboxSubscribeToOAuthState1098991175725` | Hub Summary Store (Jetbox) |
| 200 | `JetboxSubscribeToState` | Hub Summary Store (Jetbox) |
| 201 | `JetboxSubscribeToSummaries` | Hub Summary Store (Jetbox) |
| 202 | `JetboxWriteState` | Hub Summary Store (Jetbox) |
| 203 | `JetboxWriteSummary` | Hub Summary Store (Jetbox) |
| 204 | `JjAbandon` | Git, JJ, Fig & Worktrees |
| 205 | `JjCommit` | Git, JJ, Fig & Worktrees |
| 206 | `JjSquash` | Git, JJ, Fig & Worktrees |
| 207 | `JjSync` | Git, JJ, Fig & Worktrees |
| 208 | `JjUpload` | Git, JJ, Fig & Worktrees |
| 209 | `LaunchMcpApp` | MCP & Plugins |
| 210 | `ListAvailableResources` | Search & Context |
| 211 | `ListBackgroundTasks` | Terminals & Execution |
| 212 | `ListContextProviders` | Search & Context |
| 213 | `ListCustomizationPathsByFile` | Skills, Rules & Workflows |
| 214 | `ListEnvironments` | Projects & Workspaces |
| 215 | `ListGobRepos` | Git, JJ, Fig & Worktrees |
| 216 | `ListLicenses` | Enterprise & Quota |
| 217 | `ListMcpPrompts` | MCP & Plugins |
| 218 | `ListMcpResources` | MCP & Plugins |
| 219 | `ListPages` | Browser Automation |
| 220 | `ListPluginAuthProviders` | MCP & Plugins |
| 221 | `ListProfiles` | Agent Scripts & Profiles |
| 222 | `ListProjects` | Projects & Workspaces |
| 223 | `ListRemotePlugins` | MCP & Plugins |
| 224 | `ListResourceProvidersgenai` | Search & Context |
| 225 | `ListSidecarLogFiles` | Sidecars |
| 226 | `ListTerminals` | Terminals & Execution |
| 227 | `ListTriggerOptions` | Triggers & Schedules |
| 228 | `ListTriggers` | Triggers & Schedules |
| 229 | `LoadReplayConversation` | Conversation & Cascade Control |
| 230 | `LoadSharedTrajectory` | Conversation & Cascade Control |
| 231 | `LoadTrajectory` | Conversation & Cascade Control |
| 232 | `Login` | Onboarding & Auth |
| 233 | `LoginWithBrowser` | Onboarding & Auth |
| 234 | `ManageSidecar` | Sidecars |
| 235 | `MigrateApiKey` | Onboarding & Auth |
| 236 | `OpenUrl` | UI & Focus |
| 237 | `ProjectUpdatesStream` | Projects & Workspaces |
| 238 | `ProvideCompletionFeedback` | Telemetry & Analytics |
| 239 | `ReadDir` | Filesystem |
| 240 | `ReadFile` | Filesystem |
| 241 | `ReadProject` | Projects & Workspaces |
| 242 | `ReadProjects` | Projects & Workspaces |
| 243 | `ReconnectExtensionServer` | App Lifecycle & Updates |
| 244 | `RecordAnalyticsEvent` | Telemetry & Analytics |
| 245 | `RecordChatFeedback` | Telemetry & Analytics |
| 246 | `RecordChatPanelSession` | Telemetry & Analytics |
| 247 | `RecordCommitMessageSave` | Telemetry & Analytics |
| 248 | `RecordError` | Diagnostics & Debugging |
| 249 | `RecordEvent` | Telemetry & Analytics |
| 250 | `RecordInteractiveCascadeFeedbacksecurity` | Telemetry & Analytics |
| 251 | `RecordLints` | Code Intelligence |
| 252 | `RecordObservabilityData` | Telemetry & Analytics |
| 253 | `RecordSearchDocOpen` | Telemetry & Analytics |
| 254 | `RecordSearchResultsView` | Telemetry & Analytics |
| 255 | `RecordSidecarEvent` | Sidecars |
| 256 | `RecordUserGrep` | Telemetry & Analytics |
| 257 | `RecordUserStepSnapshot` | Conversation & Cascade Control |
| 258 | `RefreshContextForIdeAction` | Search & Context |
| 259 | `RefreshMcpServers` | MCP & Plugins |
| 260 | `RegisterGdmUser` | Onboarding & Auth |
| 261 | `RegisterInteraction` | Telemetry & Analytics |
| 262 | `RemoveTrackedWorkspace` | Projects & Workspaces |
| 263 | `ReplayGroundTruthTrajectory` | Conversation & Cascade Control |
| 264 | `RepoAmend` | Git, JJ, Fig & Worktrees |
| 265 | `RepoCommit` | Git, JJ, Fig & Worktrees |
| 266 | `RepoSync` | Git, JJ, Fig & Worktrees |
| 267 | `RepoUpload` | Git, JJ, Fig & Worktrees |
| 268 | `RequestAgentStatePageUpdate` | UI & Focus |
| 269 | `ResetOnboarding` | Onboarding & Auth |
| 270 | `ResolveCommandPlugin` | MCP & Plugins |
| 271 | `ResolveContextUri` | Search & Context |
| 272 | `ResolveFolder` | Filesystem |
| 273 | `ResolveOutstandingSteps` | Conversation & Cascade Control |
| 274 | `ResolveSidecarConfig` | Sidecars |
| 275 | `ResolveWorkspaceUrlPreview` | Projects & Workspaces |
| 276 | `Restart` | App Lifecycle & Updates |
| 277 | `RetrieveUserQuotaSummary` | Models & Quota |
| 278 | `RevertToCascadeStep` | Conversation & Cascade Control |
| 279 | `RunCommand` | Terminals & Execution |
| 280 | `RunTrigger` | Triggers & Schedules |
| 281 | `SaveAgentScriptCommandSpec` | Agent Scripts & Profiles |
| 282 | `SaveMediaAsArtifact` | Artifacts & Media |
| 283 | `SaveScreenRecording` | Browser & Media |
| 284 | `ScanSkillsConfigFile` | Skills, Rules & Workflows |
| 285 | `SearchCode` | Search & Context |
| 286 | `SearchContext` | Search & Context |
| 287 | `SearchConversations` | Search & Context |
| 288 | `SearchDriveFiles` | Integrations |
| 289 | `SearchFiles` | Search & Context |
| 290 | `SearchMarketplace` | MCP & Plugins |
| 291 | `SearchMarketplaceCustomizations` | MCP & Plugins |
| 292 | `SelectLicense` | Enterprise & Quota |
| 293 | `SelfAssignLicense` | Enterprise & Quota |
| 294 | `SendActionToChatPanel` | UI & Focus |
| 295 | `SendAgentMessage` | Inter-Agent Messaging |
| 296 | `SendAllQueuedMessages` | Conversation & Cascade Control |
| 297 | `SendAudioChunk` | Voice & Audio |
| 298 | `SendInputCompletionFeedback` | Telemetry & Analytics |
| 299 | `SendNarrationTurn` | Voice & Audio |
| 300 | `SendStepsToBackground` | Conversation & Cascade Control |
| 301 | `SendTerminalInput` | Terminals & Execution |
| 302 | `SendUserCascadeMessage` | Conversation & Cascade Control |
| 303 | `SetBaseExperiments` | Experiments & Flags |
| 304 | `SetBrowserOpenConversation` | Browser Automation |
| 305 | `SetCloudCodeURL` | App Lifecycle & Updates |
| 306 | `SetDefaultPluginAuthAccount` | MCP & Plugins |
| 307 | `SetMendelFlagOverrides` | Experiments & Flags |
| 308 | `SetOrVerifyStaticConfig` | Conversation & Cascade Control |
| 309 | `SetPluginAuthAccountLabel` | MCP & Plugins |
| 310 | `SetUserInfo` | User Settings & Privacy |
| 311 | `SetUserSettings` | User Settings & Privacy |
| 312 | `SetWorkingDirectories` | Projects & Workspaces |
| 313 | `SetupJetskiChat` | Conversation & Cascade Control |
| 314 | `SetupUniversitySandbox` | Permissions & Security |
| 315 | `ShouldEnableUnleash` | Experiments & Flags |
| 316 | `SignInPluginAuthProvider` | MCP & Plugins |
| 317 | `SignOutPluginAuthProvider` | MCP & Plugins |
| 318 | `SignalExecutableIdle` | App Lifecycle & Updates |
| 319 | `SimulateSegFault` | Diagnostics & Debugging |
| 320 | `SkipBrowserSubagent` | Browser Automation |
| 321 | `SkipOnboarding` | Onboarding & Auth |
| 322 | `SmartFocusConversation` | UI & Focus |
| 323 | `SmartOpenBrowser` | Browser Automation |
| 324 | `StartBattleMode` | Battle Mode (Arena) |
| 325 | `StartCascade` | Conversation & Cascade Control |
| 326 | `StartNarration` | Voice & Audio |
| 327 | `StartPluginAuthSignIn` | MCP & Plugins |
| 328 | `StartScreenRecording` | Browser & Media |
| 329 | `StatUri` | Filesystem |
| 330 | `StreamAgentStateUpdates` | Reactive Streams |
| 331 | `StreamAudioTranscription` | Reactive Streams |
| 332 | `StreamCascadePanelReactiveUpdatesDeferred` | Reactive Streams |
| 333 | `StreamCascadeReactiveUpdates` | Reactive Streams |
| 334 | `StreamCascadeSummariesReactiveUpdates` | Reactive Streams |
| 335 | `StreamSearchCode` | Reactive Streams |
| 336 | `StreamTerminalOutput` | Reactive Streams |
| 337 | `StreamTerminalShellCommand` | Reactive Streams |
| 338 | `StreamUserTrajectoryReactiveUpdatesConnection` | Reactive Streams |
| 339 | `SubscribeToAgentBrowserRequestsKeyring` | Reactive Streams |
| 340 | `SubscribeToMcpServerStates` | Reactive Streams |
| 341 | `SubscribeToPlugins` | Reactive Streams |
| 342 | `SubscribeToSidecars` | Reactive Streams |
| 343 | `ToggleMcpServer` | MCP & Plugins |
| 344 | `UpdateAgentBrowserSubscriptionruntime` | Browser Automation |
| 345 | `UpdateCascadeMemory` | Memory & Knowledge |
| 346 | `UpdateConversationAnnotations` | Conversation & Cascade Control |
| 347 | `UpdateCustomization` | Skills, Rules & Workflows |
| 348 | `UpdateCustomizationPathsFile` | Skills, Rules & Workflows |
| 349 | `UpdateDevExperiments` | Experiments & Flags |
| 350 | `UpdateEnterpriseExperimentsFromUrlcloudproxy` | Experiments & Flags |
| 351 | `UpdatePRForWorktree` | Git, JJ, Fig & Worktrees |
| 352 | `UpdatePermissionSettingsPlugin` | Permissions & Security |
| 353 | `UpdateProject` | Projects & Workspaces |
| 354 | `UpdateTrigger` | Triggers & Schedules |
| 355 | `UploadToDrive` | Integrations |
| 356 | `ValidateProject` | Projects & Workspaces |
| 357 | `ValidateTerminalSetupScript` | Terminals & Execution |
| 358 | `WaitForConversationFullyIdle` | Conversation & Cascade Control |
| 359 | `WarmUpAgentProcess` | App Lifecycle & Updates |
| 360 | `WarmUpEnvironment` | Projects & Workspaces |
| 361 | `WatchDirectory` | Filesystem |
| 362 | `WatchVersionControlState` | Git, JJ, Fig & Worktrees |
| 363 | `WellSupportedLanguages` | Code Intelligence |
| 364 | `WriteFile` | Filesystem |
| 365 | `failed` | Internal Sentinel |

## 4. Injected Antigravity Runtime Environment Variables

- `ANTIGRAVITY_AGENT=1`: Set inside agent-spawned shells.
- `ANTIGRAVITY_AGENTAPI_EXE`: Path to `/Applications/Antigravity.app/Contents/Resources/bin/language_server`.
- `ANTIGRAVITY_APP_DATA_DIR`: Path to `~/.gemini/antigravity`.
- `ANTIGRAVITY_CONVERSATION_ID`: Active conversation UUID (`cascade_id`).
- `ANTIGRAVITY_TRAJECTORY_ID`: Active trajectory UUID.
- `ANTIGRAVITY_PROJECT_ID`: Active sidebar project UUID.
- `ANTIGRAVITY_LS_ADDRESS`: Local `language_server` HTTP host:port (also recorded in `~/.gemini/antigravity/daemon/hub_<port>.json`).
- `ANTIGRAVITY_CSRF_TOKEN`: Per-daemon CSRF token for ConnectRPC requests (never print or log).
- `ANTIGRAVITY_SIDECAR_WEB_PORT` & `ANTIGRAVITY_SIDECAR_UI_TOKEN`: Set inside sidecar processes.
