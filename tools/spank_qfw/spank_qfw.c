#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <pwd.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#include <slurm/spank.h>

SPANK_PLUGIN(qfw_reservation, 1)

#define OUTPUT_LIMIT 16384
#define MAX_SERVICES 32
#define QFW_RESERVATIONS_PREFIX "QFW_RESERVATIONS="

static const char *g_helper = "/opt/openqse/qfw/bin/defw-python";
static const char *g_module = "qfw_runtime.slurm_reservation";
static const char *g_directory = "slurmctld:18090";
static const char *g_directory_name = "qfw-site-dirsvc";
static const char *g_site_config = "/etc/openqse/qfw/site.yaml";
static char *g_reservations;

static struct spank_option g_qpm_option = {
	"qfw-qpm",
	"service-id[,service-id...]",
	"reserve one or more QFw QPM services",
	1,
	0,
	NULL,
};

static void parse_plugin_args(int argc, char **argv)
{
	int i;

	for (i = 0; i < argc; i++) {
		if (strncmp(argv[i], "helper=", 7) == 0)
			g_helper = argv[i] + 7;
		else if (strncmp(argv[i], "module=", 7) == 0)
			g_module = argv[i] + 7;
		else if (strncmp(argv[i], "directory=", 10) == 0)
			g_directory = argv[i] + 10;
		else if (strncmp(argv[i], "directory-name=", 15) == 0)
			g_directory_name = argv[i] + 15;
		else if (strncmp(argv[i], "site-config=", 12) == 0)
			g_site_config = argv[i] + 12;
	}
}

static int set_helper_environment(uint32_t job_id)
{
	char endpoint[256];
	char agent_name[128];
	char *separator;

	if (snprintf(endpoint, sizeof(endpoint), "%s", g_directory) >=
	    (int)sizeof(endpoint))
		return -1;
	separator = strrchr(endpoint, ':');
	if (separator == NULL || separator == endpoint || separator[1] == '\0')
		return -1;
	*separator = '\0';
	if (snprintf(agent_name, sizeof(agent_name), "qfw-slurm-%u-%ld",
	    job_id, (long)getpid()) >= (int)sizeof(agent_name))
		return -1;
	if (setenv("QFW_SITE_CONFIG", g_site_config, 1) != 0 ||
	    setenv("QFW_SITE_DIRSVC_ENDPOINTS", g_directory, 1) != 0 ||
	    setenv("QFW_QPM_RESOLVER_SCOPE_ORDER", "site", 1) != 0 ||
	    setenv("DEFW_PARENT_HOSTNAME", endpoint, 1) != 0 ||
	    setenv("DEFW_PARENT_PORT", separator + 1, 1) != 0 ||
	    setenv("DEFW_PARENT_NAME", g_directory_name, 1) != 0 ||
	    setenv("DEFW_DISABLE_DIRSVC", "no", 1) != 0 ||
	    setenv("DEFW_AGENT_NAME", agent_name, 1) != 0 ||
	    setenv("DEFW_AGENT_TYPE", "agent", 1) != 0 ||
	    setenv("DEFW_SHELL_TYPE", "cmdline", 1) != 0 ||
	    setenv("DEFW_LISTEN_PORT", "0", 1) != 0 ||
	    setenv("DEFW_TELNET_PORT", "0", 1) != 0)
		return -1;
	return 0;
}

static int run_command(char *const command[], char *output, size_t size)
{
	int descriptors[2];
	pid_t child;
	ssize_t count;
	size_t used = 0;
	int status;

	if (pipe(descriptors) != 0)
		return -1;
	child = fork();
	if (child < 0) {
		close(descriptors[0]);
		close(descriptors[1]);
		return -1;
	}
	if (child == 0) {
		close(descriptors[0]);
		if (dup2(descriptors[1], STDOUT_FILENO) < 0)
			_exit(126);
		close(descriptors[1]);
		execv(command[0], command);
		_exit(127);
	}
	close(descriptors[1]);
	while (used + 1 < size) {
		count = read(descriptors[0], output + used, size - used - 1);
		if (count > 0) {
			used += (size_t)count;
			continue;
		}
		if (count < 0 && errno == EINTR)
			continue;
		break;
	}
	output[used] = '\0';
	close(descriptors[0]);
	while (waitpid(child, &status, 0) < 0) {
		if (errno != EINTR)
			return -1;
	}
	if (!WIFEXITED(status) || WEXITSTATUS(status) != 0)
		return -1;
	return 0;
}

static char *reservation_output(char *output)
{
	char *match = NULL;
	char *cursor = output;
	char *next;
	size_t prefix_length = strlen(QFW_RESERVATIONS_PREFIX);

	while ((next = strstr(cursor, QFW_RESERVATIONS_PREFIX)) != NULL) {
		match = next + prefix_length;
		cursor = match;
	}
	if (match == NULL)
		return NULL;
	match[strcspn(match, "\r\n")] = '\0';
	return match[0] == '\0' ? NULL : match;
}

static int reserve_qpms(const char *services, const char *owner,
	uint32_t job_id, char **reservations)
{
	char *service_copy;
	char *save = NULL;
	char *service;
	char job_text[32];
	char output[OUTPUT_LIMIT];
	char *command[16 + (MAX_SERVICES * 2)];
	char *value;
	int index = 0;
	int service_count = 0;

	service_copy = strdup(services);
	if (service_copy == NULL)
		return -1;
	(void)snprintf(job_text, sizeof(job_text), "%u", job_id);
	command[index++] = (char *)g_helper;
	command[index++] = "-m";
	command[index++] = (char *)g_module;
	command[index++] = "reserve";
	for (service = strtok_r(service_copy, ",", &save);
	     service != NULL;
	     service = strtok_r(NULL, ",", &save)) {
		if (service[0] == '\0' || service_count++ >= MAX_SERVICES) {
			free(service_copy);
			return -1;
		}
		command[index++] = "--service-id";
		command[index++] = service;
	}
	if (service_count == 0) {
		free(service_copy);
		return -1;
	}
	command[index++] = "--owner";
	command[index++] = (char *)owner;
	command[index++] = "--job-id";
	command[index++] = job_text;
	command[index++] = "--allocation-id";
	command[index++] = job_text;
	command[index] = NULL;
	if (set_helper_environment(job_id) != 0 ||
	    run_command(command, output, sizeof(output)) != 0) {
		free(service_copy);
		return -1;
	}
	value = reservation_output(output);
	if (value == NULL) {
		free(service_copy);
		return -1;
	}
	*reservations = strdup(value);
	free(service_copy);
	return *reservations == NULL ? -1 : 0;
}

static int release_qpms(const char *reservations, uint32_t job_id)
{
	char output[OUTPUT_LIMIT];
	char *command[] = {
		(char *)g_helper,
		"-m",
		(char *)g_module,
		"release",
		"--reservations",
		(char *)reservations,
		NULL,
	};

	if (set_helper_environment(job_id) != 0)
		return -1;
	return run_command(command, output, sizeof(output));
}

int slurm_spank_init(spank_t spank, int argc, char **argv)
{
	parse_plugin_args(argc, argv);
	if (spank_context() == S_CTX_LOCAL) {
		if (spank_option_register(spank, &g_qpm_option) != ESPANK_SUCCESS)
			return SLURM_ERROR;
	}
	return SLURM_SUCCESS;
}

int slurm_spank_local_user_init(spank_t spank, int argc, char **argv)
{
	char *services = NULL;
	uid_t uid;
	uint32_t job_id;
	struct passwd password;
	struct passwd *result = NULL;
	char password_buffer[4096];

	(void)argc;
	(void)argv;
	if (spank_option_getopt(spank, &g_qpm_option, &services) !=
	    ESPANK_SUCCESS || services == NULL || services[0] == '\0')
		return SLURM_SUCCESS;
	if (g_reservations != NULL)
		return setenv("QFW_RESERVATIONS", g_reservations, 1) == 0 ?
			SLURM_SUCCESS : SLURM_ERROR;
	if (spank_get_item(spank, S_JOB_UID, &uid) != ESPANK_SUCCESS ||
	    spank_get_item(spank, S_JOB_ID, &job_id) != ESPANK_SUCCESS ||
	    getpwuid_r(uid, &password, password_buffer,
	    sizeof(password_buffer), &result) != 0 || result == NULL) {
		slurm_error("spank_qfw: cannot determine trusted job identity");
		return SLURM_ERROR;
	}
	if (reserve_qpms(services, result->pw_name, job_id,
	    &g_reservations) != 0) {
		slurm_error("spank_qfw: QPM reservation failed for job %u", job_id);
		return SLURM_ERROR;
	}
	if (setenv("QFW_RESERVATIONS", g_reservations, 1) != 0) {
		slurm_error("spank_qfw: cannot export QFW_RESERVATIONS");
		(void)release_qpms(g_reservations, job_id);
		free(g_reservations);
		g_reservations = NULL;
		return SLURM_ERROR;
	}
	return SLURM_SUCCESS;
}

int slurm_spank_exit(spank_t spank, int argc, char **argv)
{
	uint32_t job_id = 0;
	int result = SLURM_SUCCESS;

	(void)argc;
	(void)argv;
	if (spank_context() != S_CTX_LOCAL || g_reservations == NULL)
		return SLURM_SUCCESS;
	(void)spank_get_item(spank, S_JOB_ID, &job_id);
	if (release_qpms(g_reservations, job_id) != 0) {
		slurm_error("spank_qfw: QPM release failed for job %u", job_id);
		result = SLURM_ERROR;
	}
	free(g_reservations);
	g_reservations = NULL;
	return result;
}
