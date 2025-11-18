# frozen_string_literal: true

require 'cgi'

module Integrations
  module GoogleCalendar
    class EventsList
      PATH_TEMPLATE = '/calendar/v3/calendars/%<calendar_id>s/events'.freeze

      def initialize(client:, calendar_id:, query: {})
        @client = client
        @calendar_id = calendar_id
        @query = query
      end

      def call
        validate_calendar_id!

        client.execute(
          function: 'GOOGLE_CALENDAR__EVENTS_LIST',
          arguments: build_arguments
        )
      rescue StandardError => error
        Rails.logger.error(
          "[Integrations::GoogleCalendar::EventsList] Failed to fetch events: #{error.message}"
        )
        raise
      end

      private

      attr_reader :client, :calendar_id, :query

      def validate_calendar_id!
        raise ArgumentError, 'calendar_id must be provided' if calendar_id.blank?
      end

      def build_arguments
        {
          # Added the missing `path` parameter so the Google Calendar integration knows
          # which endpoint to call. Without this the API rejected the request.
          path: format(PATH_TEMPLATE, calendar_id: CGI.escape(calendar_id)),
          query: query
        }
      end
    end
  end
end
