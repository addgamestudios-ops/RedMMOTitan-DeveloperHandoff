/*
 * RedMMO M07 NWIRO activation-replay direct coordinator -- REVIEW SOURCE ONLY.
 *
 * Security boundary:
 *   - This file is review material.  A future trusted, inline, 64-bit Windows
 *     PowerShell loader must carry and authenticate its literal bytes.  It must
 *     never execute this source by project pathname.
 *   - The public entry point is fixed to the one-time offline --publish mode.
 *     It accepts only already-authenticated authorization and runtime-manifest
 *     byte arrays.  It has no path, hash, command, module, or code parameters.
 *   - This revision deliberately stops with NotImplementedException before the
 *     first persistent mutation.  The stop remains mandatory until the exact
 *     runtime-manifest parser/full retained runtime graph, private transaction
 *     publication, suspended kill-on-close job launch, and independent
 *     bootstrap/replay/protected-input postflight are implemented and reviewed.
 *
 * The read-only preflight below is intentional useful review surface: it binds
 * the exact seven-member stage-two graph, locks and authenticates those sources
 * from the same retained handles, pins the physical Python executable and DLL,
 * validates the preauthenticated envelopes, resolves native Windows locations,
 * and acquires a protected single-run mutex.  It does not create, overwrite,
 * move, delete, launch, load project Python, touch Unreal, or use the network.
 *
 * Conservative language/runtime target: Windows PowerShell 5.1 Add-Type and
 * .NET Framework (no nullable annotations, records, Span, or modern syntax).
 */

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using System.Threading;
using Microsoft.Win32.SafeHandles;

namespace RedMmo.Nwiro.ActivationReplay
{
    public sealed class CoordinatorRefusalException : InvalidOperationException
    {
        public CoordinatorRefusalException(string message)
            : base(message)
        {
        }
    }

    public static class DirectPublishCoordinator
    {
        public const string AuthorizationId =
            "redmmo.m07.nwiro.activation-replay-direct-coordinator-v1";
        public const string ApprovedMode = "--publish";
        public const string FixedMutexName =
            @"Local\RedMMO.NwiroActivationReplayCoordinator.Publish.V1";
        public const string TransactionPrefix =
            @"D:\RedMMOTitanWindowsData\Staging\.NwiroActivationReplayBootstrapV1.coordinator-";
        public const string BootstrapRoot =
            @"D:\RedMMOTitanWindowsData\Staging\NwiroActivationReplayBootstrapV1";
        public const string ReplayRoot =
            @"D:\RedMMOTitanWindowsData\Staging\NwiroRestrictedProbeActivationReplayV1";
        public const string RuntimeRoot =
            @"C:\Users\user\AppData\Roaming\uv\python\cpython-3.11.15-windows-x86_64-none";
        public const string PythonExecutable =
            @"C:\Users\user\AppData\Roaming\uv\python\cpython-3.11.15-windows-x86_64-none\python.exe";

        private const string RuntimeManifestSha256 =
            "A6CBE97F22C8AB928059FFF83F7887D5819B2AF45E1FE9494BA34AD6EA4E215A";
        private const int RuntimeManifestBytes = 622905;
        private const string RuntimeVersion =
            "3.11.15 (main, Jun 23 2026, 15:20:37) [MSC v.1944 64 bit (AMD64)]";

        private const string StageTwoLauncherSha256 =
            "D27FED1D4D917D616316AA35746BCC9951C821C34BD24A0477A7095E1A5E72DA";
        private const string StageTwoAuthorizationSha256 =
            "70E38DF14A052ED797B8260EE7F7C4156F077D9C1F43A641E1216B9A7027E56C";

        private const uint GenericRead = 0x80000000U;
        private const uint FileShareRead = 0x00000001U;
        private const uint OpenExisting = 3U;
        private const uint FileAttributeNormal = 0x00000080U;
        private const uint FileAttributeDirectory = 0x00000010U;
        private const uint FileAttributeReparsePoint = 0x00000400U;
        private const uint FileFlagOpenReparsePoint = 0x00200000U;
        private const uint FileFlagBackupSemantics = 0x02000000U;
        private const uint FileFlagSequentialScan = 0x08000000U;
        private const uint InvalidFileAttributes = 0xFFFFFFFFU;
        private const int FileAttributeTagInfoClass = 9;
        private const int ErrorHandleEof = 38;

        /*
         * These constants/declarations document the reviewed future mutation
         * boundary.  No method in this revision calls the mutation/process
         * functions.  Keeping the declarations here lets review and tests bind
         * the intended native primitives without providing a partial executor.
         */
        private const uint MoveFileWriteThrough = 0x00000008U;
        private const uint CreateSuspended = 0x00000004U;
        private const uint CreateUnicodeEnvironment = 0x00000400U;
        private const uint CreateNoWindow = 0x08000000U;
        private const uint JobObjectLimitKillOnJobClose = 0x00002000U;
        private const uint JobObjectLimitActiveProcess = 0x00000008U;
        private const int JobObjectExtendedLimitInformationClass = 9;
        private const uint Infinite = 0xFFFFFFFFU;

        private static readonly GraphMember[] StageTwoGraph =
        {
            new GraphMember(
                "launcher",
                @"D:\RedMMOTitan\Tools\run_redmmo_nwiro_activation_replay_sealed.py",
                "bootstrap.py",
                30222,
                StageTwoLauncherSha256),
            new GraphMember(
                "bootstrap_authorization",
                @"D:\RedMMOTitan\Build\Automation\redmmo_nwiro_activation_replay_bootstrap_execution_authorization_v1.json",
                "bootstrap_authorization.v1.json",
                2987,
                StageTwoAuthorizationSha256),
            new GraphMember(
                "contract",
                @"D:\RedMMOTitan\Tools\validate_redmmo_nwiro_restricted_probe_candidate_contract.py",
                "contract.py",
                53011,
                "A829BC5E131BA7812E1F003F2BEA3E684D6DCA2D7CFEFAFC5048502BCBBE3B02"),
            new GraphMember(
                "creator",
                @"D:\RedMMOTitan\Tools\create_redmmo_nwiro_restricted_probe_candidate.py",
                "creator.py",
                77039,
                "28BCF5F28CB94C136355536D9E1386E21895BA597F857CC2E892E6CB336AC47E"),
            new GraphMember(
                "publisher",
                @"D:\RedMMOTitan\Tools\create_redmmo_nwiro_activation_replay.py",
                "publisher.py",
                73579,
                "C4D718666C602CB981C4603A8D621FD34BAFBEF64E93E2D48773C6921AB6D1BA"),
            new GraphMember(
                "publisher_test",
                @"D:\RedMMOTitan\Tools\tests\test_create_redmmo_nwiro_activation_replay.py",
                "publisher_test.py",
                9971,
                "8C563D619937D4EF993B9A40AFCA780DC1BC93819A5E321BBB147150F102BDF9"),
            new GraphMember(
                "replay_authorization",
                @"D:\RedMMOTitan\Build\Automation\redmmo_nwiro_activation_replay_execution_authorization_v1.json",
                "replay_authorization.v1.json",
                7699,
                "E72E8426A1F9DD35326F3259B359C6460BD584B9F0B889AFE142D0942074410A")
        };

        private static readonly GraphMember[] RuntimePins =
        {
            new GraphMember(
                "python_executable",
                PythonExecutable,
                "python.exe",
                91648,
                "AE7E969410D751D010C2CA03394FE5C53230FBF48CA7D368B897E455ECA14FBA"),
            new GraphMember(
                "python_dll",
                RuntimeRoot + @"\python311.dll",
                "python311.dll",
                5842944,
                "E1B53C741751563ECA9EAC70378DE5BE36994ADAC8C27E8EC375971579E23B50")
        };

        /*
         * Fixed publish-only entry point.
         *
         * The trusted inline loader is responsible for authenticating the
         * literal coordinator source, the coordinator authorization bytes, the
         * runtime-manifest bytes, and the System32 PowerShell/.NET identities
         * before it calls this method.  This method re-binds the immutable
         * envelope and source identities but does not broaden that authority.
         */
        public static void PublishOnly(
            byte[] preauthenticatedAuthorizationBytes,
            byte[] preauthenticatedRuntimeManifestBytes)
        {
            RequireWindows();

            byte[] authorization = CloneRequiredBytes(
                preauthenticatedAuthorizationBytes,
                "coordinator authorization",
                1024,
                1024 * 1024);
            byte[] runtimeManifest = CloneRequiredBytes(
                preauthenticatedRuntimeManifestBytes,
                "runtime manifest",
                RuntimeManifestBytes,
                RuntimeManifestBytes);

            ValidateCoordinatorAuthorizationEnvelope(authorization);
            ValidateRuntimeManifestEnvelope(runtimeManifest);

            Mutex mutex = null;
            bool mutexOwned = false;
            List<LockedInput> retained = new List<LockedInput>();
            try
            {
                mutex = CreateExclusiveProtectedMutex();
                mutexOwned = true;

                VerifySystem32Host();
                RejectPersistentTargetState();

                int index;
                for (index = 0; index < StageTwoGraph.Length; index++)
                {
                    retained.Add(LockedInput.Open(StageTwoGraph[index]));
                }

                /*
                 * Lock the physical executable and DLL now.  This is not a
                 * claim of a full runtime lock: all 4,206 files plus all 366
                 * directories recorded by the exact runtime manifest must be
                 * parsed, authenticated, opened with no write/delete sharing,
                 * and retained through child exit in the executable revision.
                 */
                for (index = 0; index < RuntimePins.Length; index++)
                {
                    retained.Add(LockedInput.Open(RuntimePins[index]));
                }

                VerifyStageTwoAuthorizationBinding(retained);
                VerifyAllRetainedInputs(retained);

                RefuseBeforeFirstPersistentMutation();
            }
            finally
            {
                DisposeReverse(retained);
                if (mutex != null)
                {
                    if (mutexOwned)
                    {
                        try
                        {
                            mutex.ReleaseMutex();
                        }
                        catch (ApplicationException)
                        {
                            /* A refusal must not be masked during teardown. */
                        }
                    }
                    mutex.Dispose();
                }
                Array.Clear(authorization, 0, authorization.Length);
                Array.Clear(runtimeManifest, 0, runtimeManifest.Length);
            }
        }

        private static void RefuseBeforeFirstPersistentMutation()
        {
            throw new NotImplementedException(
                "REVIEW_ONLY_NOT_IMPLEMENTED_BEFORE_MUTATION: " +
                "the exact runtime-manifest parser/full retained runtime locks, " +
                "private ACL transaction and same-handle no-clobber publication, " +
                "native suspended CreateProcessW kill-on-close job with minimal " +
                "environment, and independent bootstrap/replay/protected-input " +
                "postflight are not implemented in this review revision.");
        }

        private static void RequireWindows()
        {
            if (Environment.OSVersion.Platform != PlatformID.Win32NT)
            {
                throw new CoordinatorRefusalException(
                    "Windows NT is required.");
            }
            if (IntPtr.Size != 8)
            {
                throw new CoordinatorRefusalException(
                    "A 64-bit coordinator host is required.");
            }
        }

        private static byte[] CloneRequiredBytes(
            byte[] value,
            string label,
            int minimum,
            int maximum)
        {
            if (value == null)
            {
                throw new CoordinatorRefusalException(label + " is null.");
            }
            if (value.Length < minimum || value.Length > maximum)
            {
                throw new CoordinatorRefusalException(
                    label + " has a refused byte length.");
            }
            byte[] clone = new byte[value.Length];
            Buffer.BlockCopy(value, 0, clone, 0, value.Length);
            return clone;
        }

        private static void ValidateCoordinatorAuthorizationEnvelope(
            byte[] authorization)
        {
            string text = DecodeCanonicalSingleLineJson(
                authorization,
                "coordinator authorization");

            RequireContains(
                text,
                "\"authorization_id\":\"" + AuthorizationId + "\"",
                "coordinator authorization id");
            RequireContains(
                text,
                "\"approved_mode\":\"" + ApprovedMode + "\"",
                "publish-only mode");
            RequireContains(
                text,
                "\"status\":\"approved_once_offline_direct_coordinator_only\"",
                "single-use coordinator status");
            RequireContains(
                text,
                "\"bootstrap_root\":\"D:/RedMMOTitanWindowsData/Staging/NwiroActivationReplayBootstrapV1\"",
                "fixed bootstrap root");
            RequireContains(
                text,
                "\"replay_root\":\"D:/RedMMOTitanWindowsData/Staging/NwiroRestrictedProbeActivationReplayV1\"",
                "fixed replay root");
            RequireContains(
                text,
                "\"mutex\":\"Local\\\\RedMMO.NwiroActivationReplayCoordinator.Publish.V1\"",
                "fixed mutex");
            RequireContains(
                text,
                StageTwoLauncherSha256,
                "stage-two launcher digest");
            RequireContains(
                text,
                StageTwoAuthorizationSha256,
                "stage-two authorization digest");
            RequireContains(
                text,
                RuntimeManifestSha256,
                "runtime-manifest digest");
            RequireContains(
                text,
                "\"network_authorized\":false",
                "network refusal");
            RequireContains(
                text,
                "\"unreal_launch_authorized\":false",
                "Unreal refusal");
            RequireContains(
                text,
                "\"asset_or_map_mutation_authorized\":false",
                "asset/map refusal");
            RequireContains(
                text,
                "\"build_authorized\":false",
                "build refusal");
            RequireContains(
                text,
                "\"codex_config_mutation_authorized\":false",
                "Codex-config refusal");
            RequireContains(
                text,
                "\"private_bootstrap_publication_authorized\":true",
                "bootstrap publication authority");
            RequireContains(
                text,
                "\"parent_replay_publication_authorized\":true",
                "parent replay publication authority");

            if (text.IndexOf("\"allowed_modes\"", StringComparison.Ordinal) >= 0 ||
                text.IndexOf("--verify", StringComparison.Ordinal) >= 0 ||
                text.IndexOf("--run-replay", StringComparison.Ordinal) >= 0)
            {
                throw new CoordinatorRefusalException(
                    "Coordinator authorization is not bound to one publish mode.");
            }
        }

        private static void ValidateRuntimeManifestEnvelope(byte[] manifest)
        {
            RequireSha256(
                manifest,
                RuntimeManifestSha256,
                "runtime manifest");
            string text = DecodeCanonicalSingleLineJson(
                manifest,
                "runtime manifest");
            RequireContains(
                text,
                "\"manifest_id\":\"redmmo.m07.nwiro.replay-python-runtime-v1\"",
                "runtime manifest id");
            RequireContains(
                text,
                "\"status\":\"review_input_not_execution_authority\"",
                "runtime manifest status");
            RequireContains(
                text,
                "\"python_executable\":\"C:/Users/user/AppData/Roaming/uv/python/cpython-3.11.15-windows-x86_64-none/python.exe\"",
                "physical Python executable");
            RequireContains(
                text,
                "\"runtime_root\":\"C:/Users/user/AppData/Roaming/uv/python/cpython-3.11.15-windows-x86_64-none\"",
                "physical Python root");
            RequireContains(
                text,
                "\"version\":\"" + RuntimeVersion + "\"",
                "Python version");
            RequireContains(
                text,
                "\"required_flags\":[\"-I\",\"-S\",\"-B\"]",
                "isolated Python flags");
            RequireContains(
                text,
                "\"directory_count_excluding_root\":366",
                "runtime directory count");
            RequireContains(
                text,
                "\"file_count\":4206",
                "runtime file count");
            RequireContains(
                text,
                "\"total_bytes\":74504291",
                "runtime byte count");
            RequireContains(
                text,
                "\"topology_sha256\":\"1271147F093E605C143239A3BED6EE91CA7361AFC71912550C75B07CF98511C1\"",
                "runtime topology");
            RequireContains(
                text,
                "\"record_set_sha256\":\"A46015AB7005B36A0FCCEA9389426A1DDFD57E41DBC0D66EF86270A6C028CDAE\"",
                "runtime record set");
        }

        private static string DecodeCanonicalSingleLineJson(
            byte[] payload,
            string label)
        {
            if (payload.Length < 2 ||
                payload[payload.Length - 1] != (byte)'\n')
            {
                throw new CoordinatorRefusalException(
                    label + " is not newline-terminated canonical JSON.");
            }
            int index;
            for (index = 0; index < payload.Length - 1; index++)
            {
                if (payload[index] == 0 ||
                    payload[index] == (byte)'\r' ||
                    payload[index] == (byte)'\n')
                {
                    throw new CoordinatorRefusalException(
                        label + " is not single-line canonical JSON.");
                }
            }
            UTF8Encoding strictUtf8 = new UTF8Encoding(false, true);
            string text;
            try
            {
                text = strictUtf8.GetString(payload, 0, payload.Length - 1);
            }
            catch (DecoderFallbackException exception)
            {
                throw new CoordinatorRefusalException(
                    label + " is not strict UTF-8: " + exception.Message);
            }
            if (text.Length == 0 || text[0] != '{' ||
                text[text.Length - 1] != '}')
            {
                throw new CoordinatorRefusalException(
                    label + " is not a canonical JSON object.");
            }
            return text;
        }

        private static void RequireContains(
            string text,
            string marker,
            string label)
        {
            if (text.IndexOf(marker, StringComparison.Ordinal) < 0)
            {
                throw new CoordinatorRefusalException(
                    "Missing exact " + label + ".");
            }
        }

        private static void RequireSha256(
            byte[] payload,
            string expected,
            string label)
        {
            string observed;
            using (SHA256 algorithm = SHA256.Create())
            {
                observed = ToHex(algorithm.ComputeHash(payload));
            }
            if (!FixedTimeAsciiEquals(observed, expected))
            {
                throw new CoordinatorRefusalException(
                    label + " SHA-256 drift.");
            }
        }

        private static bool FixedTimeAsciiEquals(string left, string right)
        {
            if (left == null || right == null ||
                left.Length != right.Length)
            {
                return false;
            }
            int difference = 0;
            int index;
            for (index = 0; index < left.Length; index++)
            {
                difference |= left[index] ^ right[index];
            }
            return difference == 0;
        }

        private static string ToHex(byte[] value)
        {
            StringBuilder builder = new StringBuilder(value.Length * 2);
            int index;
            for (index = 0; index < value.Length; index++)
            {
                builder.Append(value[index].ToString("X2"));
            }
            return builder.ToString();
        }

        private static Mutex CreateExclusiveProtectedMutex()
        {
            WindowsIdentity identity = WindowsIdentity.GetCurrent();
            if (identity == null || identity.User == null)
            {
                throw new CoordinatorRefusalException(
                    "Current Windows SID is unavailable.");
            }

            MutexSecurity security = new MutexSecurity();
            security.SetAccessRuleProtection(true, false);
            AddMutexRule(security, identity.User);
            AddMutexRule(
                security,
                new SecurityIdentifier(WellKnownSidType.LocalSystemSid, null));
            AddMutexRule(
                security,
                new SecurityIdentifier(
                    WellKnownSidType.BuiltinAdministratorsSid,
                    null));
            security.SetOwner(identity.User);

            bool createdNew;
            Mutex mutex;
            try
            {
                mutex = new Mutex(
                    true,
                    FixedMutexName,
                    out createdNew,
                    security);
            }
            catch (UnauthorizedAccessException exception)
            {
                throw new CoordinatorRefusalException(
                    "Protected mutex could not be created: " +
                    exception.Message);
            }
            if (!createdNew)
            {
                mutex.Dispose();
                throw new CoordinatorRefusalException(
                    "The fixed coordinator mutex already exists; overlap or " +
                    "namespace squatting is refused.");
            }
            return mutex;
        }

        private static void AddMutexRule(
            MutexSecurity security,
            SecurityIdentifier identity)
        {
            security.AddAccessRule(
                new MutexAccessRule(
                    identity,
                    MutexRights.FullControl,
                    AccessControlType.Allow));
        }

        private static void VerifySystem32Host()
        {
            string windowsDirectory = GetNativeDirectory(
                NativeMethods.GetWindowsDirectory,
                "Windows directory");
            string systemDirectory = GetNativeDirectory(
                NativeMethods.GetSystemDirectory,
                "System directory");
            string expectedSystem = Path.Combine(
                windowsDirectory,
                "System32");
            if (!PathEquals(systemDirectory, expectedSystem))
            {
                throw new CoordinatorRefusalException(
                    "The native System32 directory identity drifted.");
            }

            string hostPath;
            try
            {
                using (Process process = Process.GetCurrentProcess())
                {
                    hostPath = process.MainModule.FileName;
                }
            }
            catch (Exception exception)
            {
                throw new CoordinatorRefusalException(
                    "PowerShell host identity could not be read: " +
                    exception.Message);
            }

            string expectedHost = Path.Combine(
                systemDirectory,
                @"WindowsPowerShell\v1.0\powershell.exe");
            if (!PathEquals(hostPath, expectedHost))
            {
                throw new CoordinatorRefusalException(
                    "Only native 64-bit System32 Windows PowerShell is allowed.");
            }
        }

        private delegate uint NativeDirectoryReader(
            StringBuilder buffer,
            uint size);

        private static string GetNativeDirectory(
            NativeDirectoryReader reader,
            string label)
        {
            StringBuilder buffer = new StringBuilder(32768);
            uint length = reader(buffer, (uint)buffer.Capacity);
            if (length == 0 || length >= (uint)buffer.Capacity)
            {
                throw new CoordinatorRefusalException(
                    label + " could not be resolved natively.");
            }
            string value = Path.GetFullPath(buffer.ToString());
            RejectReparseChain(value, true);
            return value;
        }

        private static void RejectPersistentTargetState()
        {
            if (File.Exists(BootstrapRoot) ||
                Directory.Exists(BootstrapRoot))
            {
                throw new CoordinatorRefusalException(
                    "The no-clobber bootstrap target already exists.");
            }
            if (File.Exists(ReplayRoot) || Directory.Exists(ReplayRoot))
            {
                throw new CoordinatorRefusalException(
                    "The no-clobber replay target already exists.");
            }

            string transactionDirectory = Path.GetDirectoryName(
                TransactionPrefix);
            if (string.IsNullOrEmpty(transactionDirectory))
            {
                throw new CoordinatorRefusalException(
                    "The fixed transaction parent is invalid.");
            }
            RejectReparseChain(transactionDirectory, true);
            VerifyNoUnapprovedWriteAcl(transactionDirectory, true);

            string[] ownedOrphans = Directory.GetFileSystemEntries(
                transactionDirectory,
                Path.GetFileName(TransactionPrefix) + "*",
                SearchOption.TopDirectoryOnly);
            if (ownedOrphans.Length != 0)
            {
                throw new CoordinatorRefusalException(
                    "A prior owned coordinator orphan exists and is preserved.");
            }
        }

        private static void VerifyStageTwoAuthorizationBinding(
            List<LockedInput> retained)
        {
            if (retained.Count < StageTwoGraph.Length)
            {
                throw new CoordinatorRefusalException(
                    "The complete stage-two graph was not retained.");
            }
            if (!FixedTimeAsciiEquals(
                    retained[0].ObservedSha256,
                    StageTwoLauncherSha256) ||
                !FixedTimeAsciiEquals(
                    retained[1].ObservedSha256,
                    StageTwoAuthorizationSha256))
            {
                throw new CoordinatorRefusalException(
                    "Stage-two launcher/authorization binding drifted.");
            }
        }

        private static void VerifyAllRetainedInputs(
            List<LockedInput> retained)
        {
            int index;
            for (index = 0; index < retained.Count; index++)
            {
                retained[index].VerifyUnchanged();
            }
        }

        private static void DisposeReverse(List<LockedInput> retained)
        {
            int index;
            for (index = retained.Count - 1; index >= 0; index--)
            {
                try
                {
                    retained[index].Dispose();
                }
                catch
                {
                    /* Preserve the primary refusal. */
                }
            }
        }

        private static void RejectReparseChain(
            string inputPath,
            bool requireLeafDirectory)
        {
            string fullPath = Path.GetFullPath(inputPath);
            string root = Path.GetPathRoot(fullPath);
            if (string.IsNullOrEmpty(root))
            {
                throw new CoordinatorRefusalException(
                    "An absolute Windows path is required.");
            }
            string relative = fullPath.Substring(root.Length);
            string[] parts = relative.Split(
                new char[] { Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar },
                StringSplitOptions.RemoveEmptyEntries);
            string current = root;
            int index;
            for (index = 0; index < parts.Length; index++)
            {
                current = Path.Combine(current, parts[index]);
                uint attributes = NativeMethods.GetFileAttributes(current);
                if (attributes == InvalidFileAttributes)
                {
                    throw new CoordinatorRefusalException(
                        "Path component is absent or unreadable: " + current);
                }
                if ((attributes & FileAttributeReparsePoint) != 0)
                {
                    throw new CoordinatorRefusalException(
                        "Reparse path component refused: " + current);
                }
                if (index != parts.Length - 1 &&
                    (attributes & FileAttributeDirectory) == 0)
                {
                    throw new CoordinatorRefusalException(
                        "Non-directory path ancestor refused: " + current);
                }
            }
            if (requireLeafDirectory)
            {
                uint leafAttributes = NativeMethods.GetFileAttributes(fullPath);
                if (leafAttributes == InvalidFileAttributes ||
                    (leafAttributes & FileAttributeDirectory) == 0)
                {
                    throw new CoordinatorRefusalException(
                        "Required directory is absent: " + fullPath);
                }
            }
        }

        private static void VerifyNoUnapprovedWriteAcl(
            string path,
            bool directory)
        {
            FileSystemSecurity security = directory
                ? (FileSystemSecurity)Directory.GetAccessControl(
                    path,
                    AccessControlSections.Owner | AccessControlSections.Access)
                : (FileSystemSecurity)File.GetAccessControl(
                    path,
                    AccessControlSections.Owner | AccessControlSections.Access);

            SecurityIdentifier owner =
                security.GetOwner(typeof(SecurityIdentifier))
                as SecurityIdentifier;
            if (owner == null || !IsApprovedWriteIdentity(owner))
            {
                throw new CoordinatorRefusalException(
                    "Unapproved ACL owner refused: " + path);
            }

            AuthorizationRuleCollection rules = security.GetAccessRules(
                true,
                true,
                typeof(SecurityIdentifier));
            FileSystemRights writeRights =
                FileSystemRights.Write |
                FileSystemRights.Modify |
                FileSystemRights.Delete |
                FileSystemRights.DeleteSubdirectoriesAndFiles |
                FileSystemRights.ChangePermissions |
                FileSystemRights.TakeOwnership |
                FileSystemRights.FullControl;

            foreach (FileSystemAccessRule rule in rules)
            {
                if (rule.AccessControlType != AccessControlType.Allow)
                {
                    continue;
                }
                SecurityIdentifier identity =
                    rule.IdentityReference as SecurityIdentifier;
                if (identity == null)
                {
                    throw new CoordinatorRefusalException(
                        "Non-SID ACL rule refused: " + path);
                }
                if ((rule.FileSystemRights & writeRights) != 0 &&
                    !IsApprovedWriteIdentity(identity))
                {
                    throw new CoordinatorRefusalException(
                        "Unapproved write-capable ACL refused: " + path);
                }
            }
        }

        private static bool IsApprovedWriteIdentity(
            SecurityIdentifier identity)
        {
            WindowsIdentity current = WindowsIdentity.GetCurrent();
            if (current != null &&
                current.User != null &&
                current.User.Equals(identity))
            {
                return true;
            }
            SecurityIdentifier system = new SecurityIdentifier(
                WellKnownSidType.LocalSystemSid,
                null);
            SecurityIdentifier administrators = new SecurityIdentifier(
                WellKnownSidType.BuiltinAdministratorsSid,
                null);
            return identity.Equals(system) ||
                identity.Equals(administrators);
        }

        private static bool PathEquals(string left, string right)
        {
            return string.Equals(
                Path.GetFullPath(left).TrimEnd('\\'),
                Path.GetFullPath(right).TrimEnd('\\'),
                StringComparison.OrdinalIgnoreCase);
        }

        private sealed class GraphMember
        {
            public readonly string Role;
            public readonly string SourcePath;
            public readonly string SealedName;
            public readonly long ExpectedBytes;
            public readonly string ExpectedSha256;

            public GraphMember(
                string role,
                string sourcePath,
                string sealedName,
                long expectedBytes,
                string expectedSha256)
            {
                Role = role;
                SourcePath = sourcePath;
                SealedName = sealedName;
                ExpectedBytes = expectedBytes;
                ExpectedSha256 = expectedSha256;
            }
        }

        private sealed class LockedInput : IDisposable
        {
            private readonly GraphMember member;
            private readonly FileStream stream;
            private readonly FileIdentity identity;
            private readonly byte[] initialBytes;
            public readonly string ObservedSha256;
            private bool disposed;

            private LockedInput(
                GraphMember memberValue,
                FileStream streamValue,
                FileIdentity identityValue,
                byte[] bytesValue,
                string sha256Value)
            {
                member = memberValue;
                stream = streamValue;
                identity = identityValue;
                initialBytes = bytesValue;
                ObservedSha256 = sha256Value;
            }

            public static LockedInput Open(GraphMember member)
            {
                string fullPath = Path.GetFullPath(member.SourcePath);
                if (!PathEquals(fullPath, member.SourcePath))
                {
                    throw new CoordinatorRefusalException(
                        "Fixed source path normalization drift: " + member.Role);
                }
                RejectReparseChain(
                    Path.GetDirectoryName(fullPath),
                    true);
                VerifyNoUnapprovedWriteAcl(fullPath, false);
                RejectNamedStreams(fullPath);

                SafeFileHandle handle = NativeMethods.CreateFile(
                    fullPath,
                    GenericRead,
                    FileShareRead,
                    IntPtr.Zero,
                    OpenExisting,
                    FileAttributeNormal |
                        FileFlagOpenReparsePoint |
                        FileFlagSequentialScan,
                    IntPtr.Zero);
                if (handle == null || handle.IsInvalid)
                {
                    int error = Marshal.GetLastWin32Error();
                    if (handle != null)
                    {
                        handle.Dispose();
                    }
                    throw new CoordinatorRefusalException(
                        "Retained source open failed for " + member.Role +
                        " (Win32 " + error.ToString() + ").");
                }

                FileStream fileStream = null;
                try
                {
                    FileAttributeTagInfo tagInfo;
                    if (!TryGetAttributeTagInfo(handle, out tagInfo) ||
                        (tagInfo.FileAttributes &
                            FileAttributeReparsePoint) != 0)
                    {
                        throw new CoordinatorRefusalException(
                            "Retained source is a reparse point: " +
                            member.Role);
                    }

                    ByHandleFileInformation nativeInfo;
                    if (!NativeMethods.GetFileInformationByHandle(
                            handle,
                            out nativeInfo))
                    {
                        throw new CoordinatorRefusalException(
                            "Retained source identity query failed: " +
                            member.Role);
                    }
                    FileIdentity openedIdentity =
                        FileIdentity.From(nativeInfo);
                    if (openedIdentity.LinkCount != 1 ||
                        openedIdentity.Length != member.ExpectedBytes)
                    {
                        throw new CoordinatorRefusalException(
                            "Retained source size/link identity drift: " +
                            member.Role);
                    }

                    fileStream = new FileStream(
                        handle,
                        FileAccess.Read,
                        65536,
                        false);
                    handle = null;
                    byte[] payload = ReadExact(
                        fileStream,
                        member.ExpectedBytes,
                        member.Role);
                    string digest;
                    using (SHA256 algorithm = SHA256.Create())
                    {
                        digest = ToHex(algorithm.ComputeHash(payload));
                    }
                    if (!FixedTimeAsciiEquals(
                            digest,
                            member.ExpectedSha256))
                    {
                        throw new CoordinatorRefusalException(
                            "Retained source SHA-256 drift: " + member.Role);
                    }
                    fileStream.Position = 0;
                    return new LockedInput(
                        member,
                        fileStream,
                        openedIdentity,
                        payload,
                        digest);
                }
                catch
                {
                    if (fileStream != null)
                    {
                        fileStream.Dispose();
                    }
                    else if (handle != null)
                    {
                        handle.Dispose();
                    }
                    throw;
                }
            }

            public void VerifyUnchanged()
            {
                if (disposed)
                {
                    throw new CoordinatorRefusalException(
                        "A retained source was disposed early: " +
                        member.Role);
                }
                ByHandleFileInformation currentNative;
                if (!NativeMethods.GetFileInformationByHandle(
                        stream.SafeFileHandle,
                        out currentNative))
                {
                    throw new CoordinatorRefusalException(
                        "Retained source recheck failed: " + member.Role);
                }
                FileIdentity current = FileIdentity.From(currentNative);
                if (!identity.Equals(current))
                {
                    throw new CoordinatorRefusalException(
                        "Retained source identity changed: " + member.Role);
                }
                stream.Position = 0;
                byte[] observed = ReadExact(
                    stream,
                    member.ExpectedBytes,
                    member.Role);
                if (!FixedTimeBytesEqual(initialBytes, observed))
                {
                    throw new CoordinatorRefusalException(
                        "Retained source bytes changed: " + member.Role);
                }
                RequireSha256(
                    observed,
                    member.ExpectedSha256,
                    "retained " + member.Role);
                stream.Position = 0;
                Array.Clear(observed, 0, observed.Length);
            }

            public void Dispose()
            {
                if (disposed)
                {
                    return;
                }
                disposed = true;
                Array.Clear(initialBytes, 0, initialBytes.Length);
                stream.Dispose();
            }
        }

        private static byte[] ReadExact(
            FileStream stream,
            long expectedLength,
            string label)
        {
            if (expectedLength < 0 || expectedLength > Int32.MaxValue)
            {
                throw new CoordinatorRefusalException(
                    "Refused retained length: " + label);
            }
            byte[] payload = new byte[(int)expectedLength];
            int offset = 0;
            while (offset < payload.Length)
            {
                int read = stream.Read(
                    payload,
                    offset,
                    payload.Length - offset);
                if (read <= 0)
                {
                    throw new CoordinatorRefusalException(
                        "Short retained read: " + label);
                }
                offset += read;
            }
            if (stream.ReadByte() != -1)
            {
                throw new CoordinatorRefusalException(
                    "Long retained read: " + label);
            }
            return payload;
        }

        private static bool FixedTimeBytesEqual(
            byte[] left,
            byte[] right)
        {
            if (left == null || right == null ||
                left.Length != right.Length)
            {
                return false;
            }
            int difference = 0;
            int index;
            for (index = 0; index < left.Length; index++)
            {
                difference |= left[index] ^ right[index];
            }
            return difference == 0;
        }

        private static bool TryGetAttributeTagInfo(
            SafeFileHandle handle,
            out FileAttributeTagInfo info)
        {
            int size = Marshal.SizeOf(typeof(FileAttributeTagInfo));
            IntPtr buffer = Marshal.AllocHGlobal(size);
            try
            {
                if (!NativeMethods.GetFileInformationByHandleEx(
                        handle,
                        FileAttributeTagInfoClass,
                        buffer,
                        (uint)size))
                {
                    info = new FileAttributeTagInfo();
                    return false;
                }
                info = (FileAttributeTagInfo)Marshal.PtrToStructure(
                    buffer,
                    typeof(FileAttributeTagInfo));
                return true;
            }
            finally
            {
                Marshal.FreeHGlobal(buffer);
            }
        }

        private static void RejectNamedStreams(string path)
        {
            Win32FindStreamData data = new Win32FindStreamData();
            IntPtr findHandle = NativeMethods.FindFirstStream(
                path,
                0,
                out data,
                0);
            if (findHandle == new IntPtr(-1))
            {
                int error = Marshal.GetLastWin32Error();
                if (error == ErrorHandleEof)
                {
                    return;
                }
                throw new CoordinatorRefusalException(
                    "Alternate-stream enumeration failed (Win32 " +
                    error.ToString() + "): " + path);
            }
            try
            {
                while (true)
                {
                    if (!string.Equals(
                            data.StreamName,
                            "::$DATA",
                            StringComparison.Ordinal))
                    {
                        throw new CoordinatorRefusalException(
                            "Named alternate stream refused: " + path);
                    }
                    if (!NativeMethods.FindNextStream(
                            findHandle,
                            out data))
                    {
                        int error = Marshal.GetLastWin32Error();
                        if (error != ErrorHandleEof)
                        {
                            throw new CoordinatorRefusalException(
                                "Alternate-stream enumeration changed " +
                                "(Win32 " + error.ToString() + "): " + path);
                        }
                        break;
                    }
                }
            }
            finally
            {
                NativeMethods.FindClose(findHandle);
            }
        }

        private sealed class FileIdentity
        {
            public readonly uint VolumeSerial;
            public readonly ulong FileIndex;
            public readonly uint LinkCount;
            public readonly long Length;
            public readonly long LastWriteFileTime;

            private FileIdentity(
                uint volumeSerial,
                ulong fileIndex,
                uint linkCount,
                long length,
                long lastWriteFileTime)
            {
                VolumeSerial = volumeSerial;
                FileIndex = fileIndex;
                LinkCount = linkCount;
                Length = length;
                LastWriteFileTime = lastWriteFileTime;
            }

            public static FileIdentity From(
                ByHandleFileInformation value)
            {
                ulong fileIndex =
                    ((ulong)value.FileIndexHigh << 32) |
                    value.FileIndexLow;
                long length =
                    ((long)value.FileSizeHigh << 32) |
                    value.FileSizeLow;
                long lastWrite =
                    ((long)value.LastWriteTime.HighDateTime << 32) |
                    value.LastWriteTime.LowDateTime;
                return new FileIdentity(
                    value.VolumeSerialNumber,
                    fileIndex,
                    value.NumberOfLinks,
                    length,
                    lastWrite);
            }

            public override bool Equals(object other)
            {
                FileIdentity value = other as FileIdentity;
                return value != null &&
                    VolumeSerial == value.VolumeSerial &&
                    FileIndex == value.FileIndex &&
                    LinkCount == value.LinkCount &&
                    Length == value.Length &&
                    LastWriteFileTime == value.LastWriteFileTime;
            }

            public override int GetHashCode()
            {
                return VolumeSerial.GetHashCode() ^
                    FileIndex.GetHashCode() ^
                    LinkCount.GetHashCode() ^
                    Length.GetHashCode() ^
                    LastWriteFileTime.GetHashCode();
            }
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct FileTime
        {
            public uint LowDateTime;
            public uint HighDateTime;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct ByHandleFileInformation
        {
            public uint FileAttributes;
            public FileTime CreationTime;
            public FileTime LastAccessTime;
            public FileTime LastWriteTime;
            public uint VolumeSerialNumber;
            public uint FileSizeHigh;
            public uint FileSizeLow;
            public uint NumberOfLinks;
            public uint FileIndexHigh;
            public uint FileIndexLow;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct FileAttributeTagInfo
        {
            public uint FileAttributes;
            public uint ReparseTag;
        }

        [StructLayout(
            LayoutKind.Sequential,
            CharSet = CharSet.Unicode)]
        private struct Win32FindStreamData
        {
            public long StreamSize;

            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 296)]
            public string StreamName;
        }

        /*
         * Future reviewed executor structures.  They are deliberately unused
         * while RefuseBeforeFirstPersistentMutation is mandatory.
         */
        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
        private struct StartupInfo
        {
            public int Cb;
            public string Reserved;
            public string Desktop;
            public string Title;
            public int X;
            public int Y;
            public int XSize;
            public int YSize;
            public int XCountChars;
            public int YCountChars;
            public int FillAttribute;
            public int Flags;
            public short ShowWindow;
            public short Reserved2;
            public IntPtr Reserved2Pointer;
            public IntPtr StandardInput;
            public IntPtr StandardOutput;
            public IntPtr StandardError;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct ProcessInformation
        {
            public IntPtr Process;
            public IntPtr Thread;
            public uint ProcessId;
            public uint ThreadId;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct IoCounters
        {
            public ulong ReadOperationCount;
            public ulong WriteOperationCount;
            public ulong OtherOperationCount;
            public ulong ReadTransferCount;
            public ulong WriteTransferCount;
            public ulong OtherTransferCount;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct BasicLimitInformation
        {
            public long PerProcessUserTimeLimit;
            public long PerJobUserTimeLimit;
            public uint LimitFlags;
            public UIntPtr MinimumWorkingSetSize;
            public UIntPtr MaximumWorkingSetSize;
            public uint ActiveProcessLimit;
            public UIntPtr Affinity;
            public uint PriorityClass;
            public uint SchedulingClass;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct ExtendedLimitInformation
        {
            public BasicLimitInformation BasicLimitInformation;
            public IoCounters IoInfo;
            public UIntPtr ProcessMemoryLimit;
            public UIntPtr JobMemoryLimit;
            public UIntPtr PeakProcessMemoryUsed;
            public UIntPtr PeakJobMemoryUsed;
        }

        private static class NativeMethods
        {
            [DllImport(
                "kernel32.dll",
                EntryPoint = "CreateFileW",
                CharSet = CharSet.Unicode,
                SetLastError = true)]
            public static extern SafeFileHandle CreateFile(
                string fileName,
                uint desiredAccess,
                uint shareMode,
                IntPtr securityAttributes,
                uint creationDisposition,
                uint flagsAndAttributes,
                IntPtr templateFile);

            [DllImport(
                "kernel32.dll",
                SetLastError = true)]
            [return: MarshalAs(UnmanagedType.Bool)]
            public static extern bool GetFileInformationByHandle(
                SafeFileHandle file,
                out ByHandleFileInformation information);

            [DllImport(
                "kernel32.dll",
                EntryPoint = "GetFileInformationByHandleEx",
                SetLastError = true)]
            [return: MarshalAs(UnmanagedType.Bool)]
            public static extern bool GetFileInformationByHandleEx(
                SafeFileHandle file,
                int informationClass,
                IntPtr information,
                uint bufferSize);

            [DllImport(
                "kernel32.dll",
                EntryPoint = "GetFileAttributesW",
                CharSet = CharSet.Unicode,
                SetLastError = true)]
            public static extern uint GetFileAttributes(string fileName);

            [DllImport(
                "kernel32.dll",
                EntryPoint = "FindFirstStreamW",
                CharSet = CharSet.Unicode,
                SetLastError = true)]
            public static extern IntPtr FindFirstStream(
                string fileName,
                int infoLevel,
                out Win32FindStreamData data,
                uint flags);

            [DllImport(
                "kernel32.dll",
                EntryPoint = "FindNextStreamW",
                CharSet = CharSet.Unicode,
                SetLastError = true)]
            [return: MarshalAs(UnmanagedType.Bool)]
            public static extern bool FindNextStream(
                IntPtr findHandle,
                out Win32FindStreamData data);

            [DllImport(
                "kernel32.dll",
                SetLastError = true)]
            [return: MarshalAs(UnmanagedType.Bool)]
            public static extern bool FindClose(IntPtr findHandle);

            [DllImport(
                "kernel32.dll",
                EntryPoint = "GetWindowsDirectoryW",
                CharSet = CharSet.Unicode,
                SetLastError = true)]
            public static extern uint GetWindowsDirectory(
                StringBuilder buffer,
                uint size);

            [DllImport(
                "kernel32.dll",
                EntryPoint = "GetSystemDirectoryW",
                CharSet = CharSet.Unicode,
                SetLastError = true)]
            public static extern uint GetSystemDirectory(
                StringBuilder buffer,
                uint size);

            [DllImport(
                "kernel32.dll",
                EntryPoint = "MoveFileExW",
                CharSet = CharSet.Unicode,
                SetLastError = true)]
            [return: MarshalAs(UnmanagedType.Bool)]
            public static extern bool MoveFileEx(
                string existingFileName,
                string newFileName,
                uint flags);

            [DllImport(
                "kernel32.dll",
                EntryPoint = "CreateProcessW",
                CharSet = CharSet.Unicode,
                SetLastError = true)]
            [return: MarshalAs(UnmanagedType.Bool)]
            public static extern bool CreateProcess(
                string applicationName,
                StringBuilder commandLine,
                IntPtr processAttributes,
                IntPtr threadAttributes,
                [MarshalAs(UnmanagedType.Bool)] bool inheritHandles,
                uint creationFlags,
                IntPtr environment,
                string currentDirectory,
                ref StartupInfo startupInfo,
                out ProcessInformation processInformation);

            [DllImport(
                "kernel32.dll",
                EntryPoint = "CreateJobObjectW",
                CharSet = CharSet.Unicode,
                SetLastError = true)]
            public static extern IntPtr CreateJobObject(
                IntPtr jobAttributes,
                string name);

            [DllImport(
                "kernel32.dll",
                SetLastError = true)]
            [return: MarshalAs(UnmanagedType.Bool)]
            public static extern bool SetInformationJobObject(
                IntPtr job,
                int informationClass,
                IntPtr information,
                uint informationLength);

            [DllImport(
                "kernel32.dll",
                SetLastError = true)]
            [return: MarshalAs(UnmanagedType.Bool)]
            public static extern bool AssignProcessToJobObject(
                IntPtr job,
                IntPtr process);

            [DllImport(
                "kernel32.dll",
                SetLastError = true)]
            public static extern uint ResumeThread(IntPtr thread);

            [DllImport(
                "kernel32.dll",
                SetLastError = true)]
            public static extern uint WaitForSingleObject(
                IntPtr handle,
                uint milliseconds);

            [DllImport(
                "kernel32.dll",
                SetLastError = true)]
            [return: MarshalAs(UnmanagedType.Bool)]
            public static extern bool GetExitCodeProcess(
                IntPtr process,
                out uint exitCode);

            [DllImport(
                "kernel32.dll",
                SetLastError = true)]
            [return: MarshalAs(UnmanagedType.Bool)]
            public static extern bool TerminateProcess(
                IntPtr process,
                uint exitCode);

            [DllImport(
                "kernel32.dll",
                SetLastError = true)]
            [return: MarshalAs(UnmanagedType.Bool)]
            public static extern bool FlushFileBuffers(IntPtr file);

            [DllImport(
                "kernel32.dll",
                SetLastError = true)]
            [return: MarshalAs(UnmanagedType.Bool)]
            public static extern bool CloseHandle(IntPtr handle);
        }
    }
}
