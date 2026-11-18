`default_nettype none
module testbench(input clock, input reset);
	reg pcpi_valid;
	reg [31:0] pcpi_insn, pcpi_rs1, pcpi_rs2;
	wire [31:0] pcpi_rd;
	wire pcpi_wr, pcpi_wait, pcpi_ready;

	picorv32_pcpi_div dut (
		.clk(clock), .resetn(!reset),
		.pcpi_valid(pcpi_valid), .pcpi_insn(pcpi_insn),
		.pcpi_rs1(pcpi_rs1), .pcpi_rs2(pcpi_rs2),
		.pcpi_wr(pcpi_wr), .pcpi_rd(pcpi_rd),
		.pcpi_wait(pcpi_wait), .pcpi_ready(pcpi_ready));

	// captured divisor magnitude N = |b| (signed modes) / b (unsigned)
	reg [31:0] h_N;
	wire h_start = dut.start;
	always @(posedge clock) begin
		if (reset) h_N <= 0;
		else if (h_start)
			h_N <= ((dut.instr_div || dut.instr_rem) && pcpi_rs2[31]) ? -pcpi_rs2 : pcpi_rs2;
	end

	always @(posedge clock) begin
		if (!reset) begin
			if ($past(!reset) && dut.running && dut.quotient_msk == 0) begin
				if (h_N != 0)
					h_term_ordering: assert(dut.dividend < h_N);
			end
			if ($past(!reset) && dut.pcpi_ready) begin
				// BAD: sampled at pcpi_ready with current (post-finish) values
				if (dut.instr_div || dut.instr_divu)
					h_branch_q: assert(dut.pcpi_rd == (dut.outsign ? -dut.quotient : dut.quotient));
				else
					h_branch_r: assert(dut.pcpi_rd == (dut.outsign ? -dut.dividend : dut.dividend));
			end
		end
	end

	always @(posedge clock) begin
		if (!reset) begin
			if (dut.running && dut.quotient_msk != 0 && dut.divisor != 0)
				h_inv: assert({32'd0, dut.dividend} < ({1'b0, dut.divisor} << 1));
		end
	end

	always @(posedge clock) begin
		if (!reset) begin
			if ($past(!reset) && dut.running && dut.quotient_msk == 0 && $past(dut.quotient_msk) == 1)
				h_last_update: assert(dut.dividend == ($past(dut.divisor) <= $past(dut.dividend)
				                                    ? $past(dut.dividend) - $past(dut.divisor)
				                                    : $past(dut.dividend)));
		end
	end
endmodule
