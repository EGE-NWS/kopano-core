/*
 * SPDX-License-Identifier: AGPL-3.0-only
 * Copyright 2005 - 2016 Zarafa and its licensors
 */
#pragma once
#include <memory>
#include <string>
#include <vector>
#include <kopano/zcdefs.h>
#include <kopano/platform.h>
#include <kopano/kcodes.h>
#include <kopano/ECChannel.h>

namespace KC {

class KC_EXPORT ECChannelClient {
public:
	ECChannelClient(const char *szPath, const char *szTokenizer);
	ECRESULT DoCmd(const std::string &strCommand, std::vector<std::string> &lstResponse);

protected:
	ECRESULT Connect();
	KC_HIDDEN ECRESULT ConnectSocket();
	KC_HIDDEN ECRESULT ConnectHttp();

	unsigned int m_ulTimeout = 5; ///< Response timeout in second

private:
	std::string m_strTokenizer, m_strPath;
	bool m_bSocket;
	uint16_t m_ulPort;
	std::unique_ptr<ECChannel> m_lpChannel;
};

} /* namespace */
