package com.tracker.api;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class TrackerApiApplication {

	public static void main(String[] args) {
		SpringApplication.run(TrackerApiApplication.class, args);
	}

}
