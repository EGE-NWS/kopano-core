/*
 * Copyright 2005-2016 Zarafa and its licensors
 * Copyright 2018, Kopano and its licensors
 *
 * This program is free software: you can redistribute it and/or modify it
 * under the terms of the GNU General Public License as published by the Free
 * Software Foundation, version 3 of the License.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program. If not, see <http://www.gnu.org/licenses/>.
 */
#include <memory>
#include <string>
#include <clocale>
#include <cstdio>
#include <cstdlib>
#include <mapidefs.h>
#include <popt.h>
#include <kopano/automapi.hpp>
#include <kopano/CommonUtil.h>
#include <kopano/ECABEntryID.h>
#include <kopano/ECConfig.h>
#include <kopano/ECLogger.h>
#include <kopano/ECRestriction.h>
#include <kopano/IECInterfaces.hpp>
#include <kopano/MAPIErrors.h>
#include <kopano/platform.h>
#include <kopano/stringutil.h>
#include <kopano/memory.hpp>
#include <kopano/charset/convert.h>
#include "ConsoleTable.h"
#include "kcore.hpp"

using namespace KCHL;

static int opt_create_store;
static const char *opt_remove_store;
static const char *opt_config_file, *opt_host;
static const char *opt_entity_name;
static std::unique_ptr<ECConfig> adm_config;

static constexpr const struct poptOption adm_options[] = {
	{nullptr, 'C', POPT_ARG_NONE, &opt_create_store, 0, "Create a store and attach it to a user account (with -n)"},
	{nullptr, 'R', POPT_ARG_STRING, &opt_remove_store, 0, "Remove an orphaned store by GUID"},
	{nullptr, 'c', POPT_ARG_STRING, &opt_config_file, 'c', "Specify alternate config file"},
	{nullptr, 'h', POPT_ARG_STRING, &opt_host, 0, "URI for server"},
	{nullptr, 'n', POPT_ARG_STRING, &opt_entity_name, 0, "User/group/company account to work on for -A,-C,-D"},
	POPT_AUTOHELP
	{nullptr}
};

static constexpr const configsetting_t adm_config_defaults[] = {
	{"server_socket", "default:"},
	{"sslkey_file", ""},
	{"sslkey_pass", ""},
	{nullptr},
};

static HRESULT adm_hex2bin(const char *x, GUID &out)
{
	auto s = hex2bin(x);
	if (s.size() != sizeof(out)) {
		ec_log_err("GUID must be exactly %zu bytes long (%zu characters in hex representation)",
			sizeof(out), 2 * sizeof(out));
		return MAPI_E_INVALID_PARAMETER;
	}
	memcpy(&out, s.c_str(), s.size());
	return hrSuccess;
}

static HRESULT adm_create_store(IECServiceAdmin *svcadm)
{
	ULONG user_size = 0, store_size = 0, root_size = 0;
	memory_ptr<ENTRYID> user_eid, store_eid, root_fld;
	auto ret = svcadm->ResolveUserName(reinterpret_cast<const TCHAR *>(opt_entity_name), 0, &user_size, &~user_eid);
	if (ret != hrSuccess)
		return kc_perror("Failed to resolve user", ret);
	ret = svcadm->CreateStore(ECSTORE_TYPE_PRIVATE, user_size, user_eid,
	      &store_size, &~store_eid, &root_size, &~root_fld);
	if (ret == MAPI_E_COLLISION)
		return kc_perror("Public store already exists", ret);
	if (ret != hrSuccess)
		return kc_perror("Unable to create store", ret);
	if (store_size == sizeof(EID))
		printf("Store GUID is %s\n", strToLower(bin2hex(sizeof(GUID), &reinterpret_cast<EID *>(store_eid.get())->guid)).c_str());
	else
		printf("Store EID is %s\n", strToLower(bin2hex(store_size, store_eid->ab)).c_str());
	return hrSuccess;
}

static HRESULT adm_remove_store(IECServiceAdmin *svcadm, const char *hexguid)
{
	GUID binguid;
	auto ret = adm_hex2bin(hexguid, binguid);
	if (ret != hrSuccess)
		return ret;
	ret = svcadm->RemoveStore(&binguid);
	if (ret != hrSuccess)
		return kc_perror("RemoveStore", ret);
	printf("The store has been removed.\n");
	return hrSuccess;
}

static HRESULT adm_perform()
{
	KServerContext srvctx;
	srvctx.m_app_misc = "storeadm";
	auto ret = srvctx.logon();
	if (ret != hrSuccess)
		return kc_perror("KServerContext::logon", ret);
	if (opt_create_store)
		return adm_create_store(srvctx.m_svcadm);
	if (opt_remove_store != nullptr)
		return adm_remove_store(srvctx.m_svcadm, opt_remove_store);
	return MAPI_E_CALL_FAILED;
}

static bool adm_parse_options(int &argc, char **&argv)
{
	adm_config.reset(ECConfig::Create(adm_config_defaults));
	opt_config_file = ECConfig::GetDefaultPath("admin.cfg");
	auto ctx = poptGetContext(nullptr, argc, const_cast<const char **>(argv), adm_options, 0);
	int c;
	while ((c = poptGetNextOpt(ctx)) >= 0) {
		if (c == 'c') {
			adm_config->LoadSettings(opt_config_file);
			if (adm_config->HasErrors()) {
				fprintf(stderr, "Error reading config file %s\n", opt_config_file);
				return false;
			}
		}
	}
	if (c < -1) {
		fprintf(stderr, "%s\n", poptStrerror(c));
		poptPrintHelp(ctx, stderr, 0);
		return false;
	}
	auto act = !!opt_create_store + !!opt_remove_store;
	if (act > 1) {
		fprintf(stderr, "-C and -R are mutually exclusive.\n");
		return false;
	} else if (act == 0) {
		fprintf(stderr, "One of -C, -R or -? must be specified.\n");
		return false;
	} else if (opt_create_store && opt_entity_name == nullptr) {
		fprintf(stderr, "-C needs the -n option\n");
		return false;
	}
	return true;
}

int main(int argc, char **argv)
{
	setlocale(LC_ALL, "");
	ec_log_get()->SetLoglevel(EC_LOGLEVEL_INFO);
	if (!adm_parse_options(argc, argv))
		return EXIT_FAILURE;
	return adm_perform() == hrSuccess ? EXIT_SUCCESS : EXIT_FAILURE;
}
